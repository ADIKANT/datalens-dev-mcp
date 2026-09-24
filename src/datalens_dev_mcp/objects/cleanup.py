from __future__ import annotations

import hashlib
import json
from collections import deque
from copy import deepcopy
from typing import Any
from uuid import uuid4

from datalens_dev_mcp.api.budget import operation_budget
from datalens_dev_mcp.operation_store import OperationStore

from datalens_dev_mcp.api.errors import (DataLensApiError, InputContractError, WritePreconditionError,
                                       error_response, safe_error_text)
from datalens_dev_mcp.api.sdk_adapter import _canonical_object_type


def _items(items: list[dict[str, Any]]) -> list[dict[str, str]]:
    result: dict[str, dict[str, str]] = {}
    for item in items:
        kind, identity = item.get("object_type"), item.get("object_id")
        if not isinstance(identity, str) or not identity.strip() or identity != identity.strip():
            raise InputContractError("cleanup requires non-empty exact object IDs")
        canonical = kind if kind == "html_page" else _canonical_object_type(kind)
        if identity in result:
            prior = _canonical_object_type(result[identity]["object_type"])
            if prior != canonical:
                raise InputContractError("conflicting cleanup types for one object identity")
            continue
        result[identity] = {"object_type": kind, "object_id": identity}
    return list(result.values())


def _absent(exc: DataLensApiError) -> bool:
    return exc.http_status == 404 and exc.response_received is True


def _relation_failure(response: dict[str, Any], phase: str) -> DataLensApiError:
    return DataLensApiError(
        response.get("error") or "incomplete dependency relations",
        method=response.get("method") or "getEntriesRelations",
        http_status=response.get("http_status"), response_received=response.get("response_received"),
        dispatch_state=response.get("dispatch_state"),
        remote_code=response.get("provider_code") or response.get("code") or "incomplete_relations",
        stage=response.get("stage") or phase, retry_after_sec=response.get("retry_after_sec"),
        request_id=response.get("request_id"), trace_id=response.get("trace_id"),
    )


class CleanupService:
    def __init__(self, *, reader: Any, deleter: Any, store: OperationStore | None = None,
                 scope: str = "local", provider_scope: str | None = None, runtime: dict[str, Any] | None = None) -> None:
        self.reader = reader
        self.deleter = deleter
        self.store = store or OperationStore()
        self.scope = scope
        self.provider_scope = provider_scope or scope
        self.runtime = runtime

    def preview(self, candidates: list[dict[str, Any]], *, preserve_roots: list[dict[str, Any]],
                budget_sec: float = 120, max_provider_calls: int = 200) -> dict[str, Any]:
        with operation_budget(budget_sec, max_provider_calls) as budget:
            return self._preview(candidates, preserve_roots=preserve_roots, budget=budget)

    def _preview(self, candidates: list[dict[str, Any]], *, preserve_roots: list[dict[str, Any]],
                 budget: Any) -> dict[str, Any]:
        # IDs identify entries within this reader's provider context; aliases only select dispatch.
        normalized, roots = _items(candidates), _items(preserve_roots)
        by_id = {item["object_id"]: item for item in normalized}
        preserve: set[str] = set()
        graph: dict[str, list[str]] = {}
        consumers: dict[str, list[str]] = {}
        issues: list[dict[str, Any]] = []
        completed_reads: list[dict[str, str]] = []
        required_reads = {(kind, item["object_id"]) for item in normalized for kind in ("object", "from", "to")}
        required_reads.update((kind, item["object_id"]) for item in roots for kind in ("object", "from"))
        read_cache: dict[tuple[str, str], Any] = {}

        def report_reads() -> None:
            # Replace an immutable snapshot for the stdio deadline responder;
            # it must never traverse a graph/cache while the worker mutates it.
            pending = [{"object_id": identity, "read": kind}
                       for kind, identity in sorted(required_reads - set(read_cache))]
            budget.read_progress = {"completed_reads": list(completed_reads), "remaining_reads": pending,
                                    "completed_read_count": len(completed_reads), "remaining_read_count": len(pending),
                                    "remaining_count_kind": "known; undiscovered dependencies may add reads"}

        report_reads()

        def get(item: dict[str, str]) -> Any:
            key = ("object", item["object_id"])
            if key not in read_cache:
                budget.phase = "object_read"
                report_reads()
                budget.check()
                read_cache[key] = self.reader.object_get(item["object_type"], item["object_id"], branch="saved")
                completed_reads.append({"object_id": item["object_id"], "read": "object"})
                report_reads()
            return read_cache[key]

        def issue(identity: str, exc: Exception) -> None:
            if isinstance(exc, DataLensApiError):
                detail = error_response(exc)
            else:
                detail = {"code": "incomplete_relations", "error": safe_error_text(exc),
                          "next_action": "Resolve incomplete provider evidence before deletion."}
            issues.append({"object_id": identity, "phase": budget.phase, **detail})
        snapshots: dict[str, Any] = {}

        def related(identity: str, direction: str) -> list[str]:
            key = (direction, identity)
            required_reads.add(key)
            if key in read_cache:
                return read_cache[key]
            budget.phase = "dependencies" if direction == "from" else "consumers"
            report_reads()
            budget.check()
            response = self.reader.object_relations(identity, direction=direction)
            if response.get("complete") is not True:
                raise _relation_failure(response, budget.phase)
            relations = response.get("relations")
            if not isinstance(relations, list) or any(
                not isinstance(x.get("id"), str) or not x["id"] for x in relations
            ):
                raise InputContractError("invalid dependency relations")
            result = sorted({x["id"] for x in relations})
            read_cache[key] = result
            completed_reads.append({"object_id": identity, "read": direction})
            report_reads()
            return result

        for root in roots:
            try:
                snapshots[root["object_id"]] = get(root)
            except (DataLensApiError, ValueError, TypeError) as exc:
                issue(root["object_id"], exc)
        queue = deque(item["object_id"] for item in roots)
        while queue:
            identity = queue.popleft()
            if identity in preserve:
                continue
            preserve.add(identity)
            try:
                graph[identity] = related(identity, "from")
                required_reads.update(("from", dependency) for dependency in graph[identity])
                queue.extend(graph[identity])
            except (DataLensApiError, ValueError, TypeError) as exc:
                issue(identity, exc)

        # Explicit outbound and inbound reads: inventory order is never dependency order.
        # Public API linkDirection=from gives dependencies; to gives consumers.
        for item in normalized:
            identity = item["object_id"]
            try:
                snapshots[identity] = get(item)
            except (DataLensApiError, ValueError, TypeError) as exc:
                if isinstance(exc, DataLensApiError) and _absent(exc) and identity not in preserve:
                    snapshots[identity] = {"absent": True}
                    graph[identity], consumers[identity] = [], []
                    read_cache[("object", identity)] = snapshots[identity]
                    completed_reads.append({"object_id": identity, "read": "object"})
                    required_reads.difference_update({("from", identity), ("to", identity)})
                else:
                    issue(identity, exc)
                continue
            try:
                graph[identity] = related(identity, "from")
                consumers[identity] = related(identity, "to")
                if identity not in preserve and any(x not in by_id or x in preserve for x in consumers[identity]):
                    issues.append({"object_id": identity, "code": "dependency_conflict", "phase": "consumers",
                                   "error": "candidate has external or preserved consumers"})
            except (DataLensApiError, ValueError, TypeError) as exc:
                issue(identity, exc)

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
            issues.append({"error": "cyclic cleanup dependencies", "object_id": "", "code": "dependency_conflict"})
        body = {
            "complete": not issues,
            "candidates": normalized,
            "preserve_roots": roots,
            "preserve": [item for item in normalized if item["object_id"] in preserve],
            "delete": [by_id[identity] for identity in order],
            "dependency_fingerprint": _digest({
                "graph": graph, "consumers": consumers,
                "snapshots": {key: _cleanup_snapshot(value) for key, value in snapshots.items()},
            }),
            "issues": issues,
            "scope": "exact candidates and API-visible relations; no tenant-wide inventory claim",
        }
        code = issues[0]["code"] if issues else "complete"
        observed = {identity: {"identity": snapshot.get("identity"),
                               "snapshot_digest": _digest(_cleanup_snapshot(snapshot)),
                               "workbook_id": (snapshot.get("object") or {}).get("workbookId")
                               or ((snapshot.get("object") or {}).get("entry") or {}).get("workbookId")}
                    for identity, snapshot in snapshots.items()}
        pending_reads = [{"object_id": identity, "read": kind}
                         for kind, identity in sorted(required_reads - set(read_cache))]
        return {"ok": not issues, **body, "status": code, "code": code,
                "operation_id": "cleanup-" + uuid4().hex, "auth_scope": self.scope,
                "preview_digest": _digest(body),
                "observed_objects": observed,
                "progress": {**budget.progress(), "completed_reads": completed_reads, "remaining_reads": pending_reads,
                             "completed_read_count": len(completed_reads), "remaining_read_count": len(pending_reads),
                             "remaining_count_kind": "known; undiscovered dependencies may add reads"},
                **({"next_action": issues[0].get("next_action", "Resolve the reported dependency conflict.")}
                   if issues else {})}

    def apply(self, preview: dict[str, Any], *, confirmed_delete: list[dict[str, Any]],
              operation_id: str | None = None, budget_sec: float = 120,
              max_provider_calls: int = 200) -> dict[str, Any]:
        with operation_budget(budget_sec, max_provider_calls), self.store.cleanup_lock(self.provider_scope):
            return self._apply(preview, confirmed_delete=confirmed_delete, operation_id=operation_id,
                               budget_sec=budget_sec, max_provider_calls=max_provider_calls)

    def _apply(self, preview: dict[str, Any], *, confirmed_delete: list[dict[str, Any]],
               operation_id: str | None, budget_sec: float, max_provider_calls: int) -> dict[str, Any]:
        if preview.get("complete") is not True:
            raise InputContractError("cleanup requires a complete dependency preview")
        expected = _items(preview.get("delete") or [])
        if _items(confirmed_delete) != expected:
            raise InputContractError("confirmed_delete must exactly match the ordered cleanup preview")
        body = {key: preview[key] for key in ("complete", "candidates", "preserve_roots", "preserve", "delete",
                                             "dependency_fingerprint", "issues", "scope") if key in preview}
        if preview.get("preview_digest") != _digest(body) or "candidates" not in body or "preserve_roots" not in body:
            raise InputContractError("cleanup preview digest does not match its contents")
        if preview.get("auth_scope", self.scope) != self.scope:
            raise InputContractError("cleanup preview belongs to a different authentication scope")
        oid = operation_id or preview.get("operation_id") or "cleanup-" + uuid4().hex
        request_digest = _digest({"scope": self.scope, "delete": expected, "preserve_roots": body["preserve_roots"],
                                  "preview_digest": preview["preview_digest"]})
        prior = self.store.get(oid)
        if prior is not None:
            if prior.get("request_digest") != request_digest:
                raise InputContractError("operation_id is already bound to a different request")
            if prior.get("status") != "preview_changed" or any(
                item.get("dispatch_state") != "not_dispatched" for item in prior.get("results", [])
            ):
                return self._reconcile(oid, budget_sec=budget_sec, max_provider_calls=max_provider_calls)
        record = {"ok": False, "operation_id": oid, "effect": "cleanup", "status": "pending",
                  "request_digest": request_digest, "auth_scope": self.scope,
                  "provider_scope": self.provider_scope, "runtime": self.runtime,
                  "ordered_delete_digest": _digest(expected), "preserve_roots": body["preserve_roots"],
                  "dependency_fingerprint": body["dependency_fingerprint"],
                  "preview_digest": preview["preview_digest"],
                  "results": [{**item, "target": item, "status": "skipped", "dispatch_state": "not_dispatched",
                               "effect_outcome": "not_applied"} for item in expected]}
        if prior is not None:
            record = prior
            record.update(status="pending", ok=False)
            self.store.put(record)
            admitted = True
        else:
            admitted, record = self.store.claim(record)
        if not admitted:
            return record
        with operation_budget(budget_sec, max_provider_calls) as budget:
            fresh = self._preview(body["candidates"], preserve_roots=body["preserve_roots"], budget=budget)
            if not fresh["complete"] or fresh["preview_digest"] != preview["preview_digest"]:
                record.update(status="preview_changed", preview=fresh, new_delete_dispatched=False,
                              progress=budget.progress(), next_action="No new delete was dispatched in this operation. "
                              "This says nothing about an older operation's unknown effect; reconcile its own receipt.")
                return self.store.put(record)
            record["observed_objects"] = fresh["observed_objects"]
            self.store.put(record)
            for item in record["results"]:
                attempted = False
                returned = False
                try:
                    budget.phase = "delete_preflight"
                    budget.check()
                    target_snapshot = self._read_if_present(item)
                    if target_snapshot is None:
                        item.update(status="already_absent", absence_verified=True)
                        record = self._save(record, budget)
                        continue
                    # The full preview is required once; immediately before each effect,
                    # revalidate only its target, consumers and preserve-root revisions.
                    for target in [item, *body["preserve_roots"]]:
                        budget.check()
                        current = (target_snapshot if target is item else
                                   self.reader.object_get(target["object_type"], target["object_id"], branch="saved"))
                        observed = fresh["observed_objects"][target["object_id"]]
                        if _digest(_cleanup_snapshot(current)) != observed["snapshot_digest"]:
                            raise WritePreconditionError("cleanup target or preserve root changed before delete")
                    budget.phase = "consumer_preflight"
                    live = self.reader.object_relations(item["object_id"], direction="to")
                    if live.get("complete") is not True:
                        raise _relation_failure(live, budget.phase)
                    absent_ids = {row["object_id"] for row in record["results"] if row.get("absence_verified")}
                    if any(consumer.get("id") not in absent_ids for consumer in live.get("relations", [])):
                        raise WritePreconditionError("cleanup target acquired a remaining consumer before delete")
                    budget.check()
                    item.update(status="uncertain", dispatch_state="dispatch_pending", effect_outcome="unknown")
                    # Durable admission precedes the SDK call, including its internal target lookup.
                    self._save(record, budget)
                    budget.phase = "delete"
                    budget.check()
                    attempted = True
                    self.deleter.delete(item["object_type"], item["object_id"])
                    returned = True
                    item.update(write_returned=True, dispatch_state="dispatched")
                    self._save(record, budget)
                    budget.phase = "absence_readback"
                    budget.check()
                    if self._already_absent(item):
                        item.update(status="deleted", absence_verified=True, effect_outcome="applied")
                    else:
                        item.update(status="uncertain", code="write_outcome_unknown",
                                    error="object remains readable after delete")
                except Exception as exc:  # noqa: BLE001 - persist each effect before returning
                    detail = error_response(exc, effect_possible=attempted)
                    if attempted and isinstance(exc, DataLensApiError) and _absent(exc):
                        try:
                            budget.check()
                            absent = self._already_absent(item)
                        except Exception:  # noqa: BLE001 - 404 from delete is not absence evidence
                            absent = False
                        if absent:
                            item.update(status="already_absent", absence_verified=True, effect_outcome="applied")
                            self._save(record, budget)
                            continue
                        detail.update(code="write_outcome_unknown", effect_outcome="unknown", dispatch_state="dispatched")
                    if returned:
                        # A readback timeout or cancellation cannot negate a preceding delete response.
                        detail.update(code="write_outcome_unknown", effect_outcome="unknown", dispatch_state="dispatched")
                    if not attempted:
                        detail.update(dispatch_state="not_dispatched", effect_outcome="not_applied")
                    item.update(detail, status="uncertain" if detail.get("effect_outcome") == "unknown" else "failed")
                self._save(record, budget)
                if item["status"] in {"failed", "uncertain"}:
                    break
            return self._save(record, budget)

    def _save(self, record: dict[str, Any], budget: Any) -> dict[str, Any]:
        statuses = {item["status"] for item in record["results"]}
        status = ("uncertain" if "uncertain" in statuses else "failed" if "failed" in statuses
                  else "partial" if "skipped" in statuses else "completed_with_absent" if "already_absent" in statuses
                  else "completed")
        record.update(status=status, ok=status in {"completed", "completed_with_absent"}, progress=budget.progress())
        if not record["ok"]:
            record["next_action"] = "Inspect this operation_id and reconcile exact targets; do not replay an unknown delete."
        else:
            record.pop("next_action", None)
        self.store.put(record)
        return record

    def reconcile(self, operation_id: str, *, budget_sec: float = 120,
                  max_provider_calls: int = 200) -> dict[str, Any]:
        with self.store.cleanup_lock(self.provider_scope):
            return self._reconcile(operation_id, budget_sec=budget_sec, max_provider_calls=max_provider_calls)

    def _reconcile(self, operation_id: str, *, budget_sec: float, max_provider_calls: int) -> dict[str, Any]:
        record = self.store.get(operation_id)
        if record is None:
            return {"ok": False, "status": "not_found", "operation_id": operation_id, "write_replayed": False}
        if record.get("auth_scope") != self.scope:
            return {"ok": False, "status": "scope_changed", "operation_id": operation_id, "write_replayed": False,
                    "next_action": "Restore the recorded authentication context before reconciling exact targets."}
        with operation_budget(budget_sec, max_provider_calls) as budget:
            budget.phase = "reconcile"
            for item in record["results"]:
                if item["status"] != "uncertain":
                    continue
                try:
                    budget.check()
                    if self._already_absent(item):
                        item.update(status="already_absent", absence_verified=True, effect_outcome="applied",
                                    evidence="exact saved-object readback returned confirmed HTTP 404")
                    else:
                        # A still-readable object does not prove an admitted request cannot apply later.
                        item.update(evidence="object remains readable; prior dispatch outcome is still unknown")
                except Exception as exc:  # noqa: BLE001 - preserve the earlier admission
                    item["reconciliation_error"] = error_response(exc)
                self._save(record, budget)
            record["write_replayed"] = False
            return self._save(record, budget)

    def _already_absent(self, item: dict[str, Any]) -> bool:
        return self._read_if_present(item) is None

    def _read_if_present(self, item: dict[str, Any]) -> dict[str, Any] | None:
        try:
            return self.reader.object_get(item["object_type"], item["object_id"], branch="saved")
        except DataLensApiError as exc:
            if _absent(exc):
                return None
            raise


def _digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _cleanup_snapshot(snapshot: Any) -> Any:
    """Canonicalize only Dataset lists whose provider order is not semantic."""
    result = deepcopy(snapshot)
    payload = result.get("object") if isinstance(result, dict) else None
    if not isinstance(payload, dict) or not isinstance(payload.get("dataset"), dict):
        return result

    def sort_list_at(value: Any, *path: str) -> None:
        for key in path[:-1]:
            value = value.get(key) if isinstance(value, dict) else None
        if isinstance(value, dict) and isinstance(value.get(path[-1]), list):
            value[path[-1]].sort(key=_digest)

    options = payload.get("options")
    sort_list_at(options, "sources", "compatible_types")
    sort_list_at(options, "join", "types")
    connections = options.get("connections") if isinstance(options, dict) else None
    items = connections.get("items") if isinstance(connections, dict) else None
    for item in items if isinstance(items, list) else []:
        sort_list_at(item, "replacement_types")
    auxiliary = payload["dataset"].get("result_schema_aux")
    dependencies = auxiliary.get("inter_dependencies") if isinstance(auxiliary, dict) else None
    deps = dependencies.get("deps") if isinstance(dependencies, dict) else None
    for dependency in deps if isinstance(deps, list) else []:
        sort_list_at(dependency, "ref_field_ids")
    return result
