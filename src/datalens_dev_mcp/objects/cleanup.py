from __future__ import annotations

import hashlib
import json
from collections import deque
from typing import Any

from datalens_dev_mcp.api.errors import DataLensApiError, UncertainWriteError, safe_error_text
from datalens_dev_mcp.api.sdk_adapter import _canonical_object_type


def _items(items: list[dict[str, Any]]) -> list[dict[str, str]]:
    result: dict[str, dict[str, str]] = {}
    for item in items:
        kind, identity = item.get("object_type"), item.get("object_id")
        if not isinstance(identity, str) or not identity.strip() or identity != identity.strip():
            raise ValueError("cleanup requires non-empty exact object IDs")
        canonical = kind if kind == "html_page" else _canonical_object_type(kind)
        if identity in result:
            prior = _canonical_object_type(result[identity]["object_type"])
            if prior != canonical:
                raise ValueError("conflicting cleanup types for one object identity")
            continue
        result[identity] = {"object_type": kind, "object_id": identity}
    return list(result.values())


def _absent(exc: DataLensApiError) -> bool:
    return exc.http_status == 404 and exc.response_received is True


class CleanupService:
    def __init__(self, *, reader: Any, deleter: Any) -> None:
        self.reader = reader
        self.deleter = deleter

    def preview(self, candidates: list[dict[str, Any]], *, preserve_roots: list[dict[str, Any]]) -> dict[str, Any]:
        # IDs identify entries within this reader's provider context; aliases only select dispatch.
        normalized, roots = _items(candidates), _items(preserve_roots)
        by_id = {item["object_id"]: item for item in normalized}
        preserve: set[str] = set()
        graph: dict[str, list[str]] = {}
        consumers: dict[str, list[str]] = {}
        issues: list[dict[str, str]] = []
        snapshots: dict[str, Any] = {}

        def related(identity: str, direction: str) -> list[str]:
            response = self.reader.object_relations(identity, direction=direction)
            if response.get("complete") is not True:
                raise ValueError("incomplete dependency relations")
            relations = response.get("relations")
            if not isinstance(relations, list) or any(
                not isinstance(x.get("id"), str) or not x["id"] for x in relations
            ):
                raise ValueError("invalid dependency relations")
            return sorted({x["id"] for x in relations})

        for root in roots:
            try:
                snapshots["root:" + root["object_id"]] = self.reader.object_get(
                    root["object_type"], root["object_id"], branch="saved"
                )
            except (DataLensApiError, ValueError, TypeError) as exc:
                issues.append({"object_id": root["object_id"], "error": safe_error_text(exc)})
        queue = deque(item["object_id"] for item in roots)
        while queue:
            identity = queue.popleft()
            if identity in preserve:
                continue
            preserve.add(identity)
            try:
                graph[identity] = related(identity, "to")
                queue.extend(graph[identity])
            except (DataLensApiError, ValueError, TypeError) as exc:
                issues.append({"object_id": identity, "error": safe_error_text(exc)})

        # Explicit outbound and inbound reads: inventory order is never dependency order.
        # Public API linkDirection=to gives dependencies; from gives consumers.
        for item in normalized:
            identity = item["object_id"]
            try:
                snapshots[identity] = self.reader.object_get(item["object_type"], identity, branch="saved")
            except DataLensApiError as exc:
                if _absent(exc) and identity not in preserve:
                    snapshots[identity] = {"absent": True}
                    graph[identity], consumers[identity] = [], []
                else:
                    issues.append({"object_id": identity, "error": safe_error_text(exc)})
                continue
            try:
                graph[identity] = related(identity, "to")
                consumers[identity] = related(identity, "from")
                if identity not in preserve and any(x not in by_id or x in preserve for x in consumers[identity]):
                    raise ValueError("candidate has external or preserved consumers")
            except (DataLensApiError, ValueError, TypeError) as exc:
                issues.append({"object_id": identity, "error": safe_error_text(exc)})

        selected = [identity for identity in by_id if identity not in preserve]
        edges = {identity: set(graph.get(identity, [])) & set(selected) for identity in selected}
        # Inbound evidence also contributes edges; do not lose a consumer reported only there.
        for dependency in selected:
            for consumer in consumers.get(dependency, []):
                if consumer in edges:
                    edges[consumer].add(dependency)
        incoming = {identity: 0 for identity in selected}
        for dependencies in edges.values():
            for dependency in dependencies:
                incoming[dependency] += 1
        ready = deque(identity for identity in selected if incoming[identity] == 0)
        order = []
        while ready:
            identity = ready.popleft()
            order.append(identity)
            for dependency in selected:
                if dependency in edges[identity]:
                    incoming[dependency] -= 1
                    if incoming[dependency] == 0:
                        ready.append(dependency)
        if len(order) != len(selected):
            issues.append({"error": "cyclic cleanup dependencies", "object_id": ""})
        body = {
            "complete": not issues,
            "candidates": normalized,
            "preserve_roots": roots,
            "preserve": [item for item in normalized if item["object_id"] in preserve],
            "delete": [by_id[identity] for identity in order],
            "dependency_fingerprint": _digest({"graph": graph, "consumers": consumers, "snapshots": snapshots}),
            "issues": issues,
            "scope": "exact candidates and API-visible relations; no tenant-wide inventory claim",
        }
        return {"ok": not issues, **body, "preview_digest": _digest(body)}

    def apply(self, preview: dict[str, Any], *, confirmed_delete: list[dict[str, Any]]) -> dict[str, Any]:
        if preview.get("complete") is not True:
            raise ValueError("cleanup requires a complete dependency preview")
        expected = _items(preview.get("delete") or [])
        if _items(confirmed_delete) != expected:
            raise ValueError("confirmed_delete must exactly match the ordered cleanup preview")
        body = {key: value for key, value in preview.items() if key not in {"ok", "preview_digest"}}
        if preview.get("preview_digest") != _digest(body) or "candidates" not in body or "preserve_roots" not in body:
            raise ValueError("cleanup preview digest does not match its contents")
        fresh = self.preview(body["candidates"], preserve_roots=body["preserve_roots"])
        if not fresh["complete"] or fresh["preview_digest"] != preview["preview_digest"]:
            return {
                "ok": False,
                "status": "preview_changed",
                "preview": fresh,
                "results": [{**item, "status": "skipped"} for item in expected],
            }
        results: list[dict[str, Any]] = []
        stopped = False
        for item in expected:
            if stopped:
                results.append({**item, "status": "skipped"})
                continue
            mutation_returned = False
            try:
                if self._already_absent(item):
                    results.append({**item, "status": "already_absent", "absence_verified": True})
                    continue
                self.deleter.delete(item["object_type"], item["object_id"])
                mutation_returned = True
                if self._already_absent(item):
                    result = {**item, "status": "deleted", "absence_verified": True}
                else:
                    result = {**item, "status": "uncertain", "error": "object remains readable after delete"}
            except DataLensApiError as exc:
                if _absent(exc):
                    try:
                        verified = self._already_absent(item)
                    except DataLensApiError:
                        verified = False
                    result = (
                        {**item, "status": "already_absent", "absence_verified": True}
                        if verified
                        else {**item, "status": "uncertain", "error": "delete 404 without verified object absence"}
                    )
                else:
                    uncertain = (
                        mutation_returned or isinstance(exc, UncertainWriteError) or exc.response_received is not True
                    )
                    result = {**item, "status": "uncertain" if uncertain else "failed", "error": safe_error_text(exc)}
            except Exception as exc:  # noqa: BLE001 - preserve partial effects after an unexpected write failure
                result = {**item, "status": "uncertain", "error": safe_error_text(exc)}
            results.append(result)
            stopped = result["status"] in {"failed", "uncertain"}
        absent = any(item["status"] == "already_absent" for item in results)
        return {
            "ok": not stopped,
            "status": "failed" if stopped else "completed_with_absent" if absent else "completed",
            "results": results,
        }

    def _already_absent(self, item: dict[str, Any]) -> bool:
        try:
            self.reader.object_get(item["object_type"], item["object_id"], branch="saved")
        except DataLensApiError as exc:
            if _absent(exc):
                return True
            raise
        return False


def _digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
