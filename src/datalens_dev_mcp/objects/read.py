from __future__ import annotations

import base64
import json
import re
from collections.abc import Mapping
from typing import Any, Protocol

from datalens_dev_mcp.objects.relations import compact_object_index, object_identity, relation_entries


class ReadApi(Protocol):
    def read(self, method: str, payload: dict[str, Any]) -> dict[str, Any]: ...


class ReadSdk(Protocol):
    def get_object(
        self,
        object_type: str,
        object_id: str,
        *,
        branch: str = "saved",
        revision_id: str | None = None,
    ) -> dict[str, Any]: ...


class ObjectReadService:
    def __init__(self, *, api: ReadApi, sdk: ReadSdk) -> None:
        self.api = api
        self.sdk = sdk

    def workbooks_list(self, *, page_size: int = 100, max_pages: int = 100) -> dict[str, Any]:
        return self._paginate("getWorkbooksList", {}, page_size=page_size, max_pages=max_pages)

    def workbook_entries(
        self,
        workbook_id: str,
        *,
        page_size: int = 100,
        max_pages: int = 100,
    ) -> dict[str, Any]:
        return self._paginate(
            "getWorkbookEntries",
            {"workbookId": workbook_id},
            page_size=page_size,
            max_pages=max_pages,
        )

    def _paginate(
        self,
        method: str,
        base_payload: dict[str, Any],
        *,
        page_size: int,
        max_pages: int,
    ) -> dict[str, Any]:
        if not 1 <= page_size <= 1000:
            raise ValueError("page_size must be between 1 and 1000")
        if not 1 <= max_pages <= 1000:
            raise ValueError("max_pages must be between 1 and 1000")
        objects: dict[str, dict[str, Any]] = {}
        token = ""
        pages = 0
        while pages < max_pages:
            payload = {**base_payload, "pageSize": page_size}
            if token:
                payload["pageToken"] = token
            raw = self.api.read(method, payload)
            page = _unwrap(raw)
            values = page.get("entries") or page.get("workbooks") or []
            if not isinstance(values, list):
                raise TypeError(f"{method} response does not contain a list")
            for item in values:
                if isinstance(item, Mapping):
                    object_id, _ = object_identity(item)
                    if object_id:
                        objects[object_id] = dict(item)
            pages += 1
            token = str(page.get("nextPageToken") or "").strip()
            if not token:
                break
        complete = not token
        return {
            "ok": True,
            "complete": complete,
            "partial_reason": "" if complete else "page_limit_reached",
            "page_count": pages,
            "object_count": len(objects),
            "next_page_token": token or None,
            "objects": compact_object_index(objects.values()),
        }

    def object_get(
        self,
        object_type: str,
        object_id: str,
        *,
        branch: str = "saved",
        revision_id: str | None = None,
        view: str = "full",
        fields: list[str] | None = None,
    ) -> dict[str, Any]:
        _validate_view(view, fields)
        if object_type == "html_page":
            request = {"entryId": object_id, "branch": branch}
            if revision_id:
                request["revId"] = revision_id
            payload = dict(_unwrap(self.api.read("getHtmlPage", request)))
        else:
            payload = self.sdk.get_object(object_type, object_id, branch=branch, revision_id=revision_id)
        observed_id, observed_type = object_identity(payload)
        if observed_id and observed_id != object_id:
            raise ValueError("provider object identity mismatch; re-read the exact target")
        known_types = {
            "dashboard",
            "dataset",
            "connection",
            "wizard_chart",
            "editor_chart",
            "ql_chart",
            "html_page",
            "workbook",
        }
        if observed_type in known_types and observed_type != object_type:
            raise ValueError("provider object type mismatch; re-read the exact target")
        entry = payload.get("entry") if isinstance(payload.get("entry"), Mapping) else {}
        observed_branch = payload.get("branch") or entry.get("branch")
        if object_type not in {"workbook", "connection", "dataset"} and observed_branch and observed_branch != branch:
            raise ValueError("provider object branch mismatch; re-read the exact branch")
        actual_revision = _revision_id(payload, branch=branch, fallback=revision_id)
        unbranched = object_type in {"workbook", "connection", "dataset"}
        result = {
            "ok": True,
            "identity": {
                "object_type": object_type,
                "object_id": object_id,
                "branch": "unbranched" if unbranched else branch,
                "revision_id": actual_revision or None,
            },
            "object": payload,
        }
        return _read_view(result, view=view, fields=fields, branch=branch)

    def object_relations(
        self,
        object_id: str,
        *,
        direction: str = "to",
        page_size: int = 100,
        max_pages: int = 100,
        page_token: str | None = None,
    ) -> dict[str, Any]:
        if not 1 <= page_size <= 1000 or not 1 <= max_pages <= 1000:
            raise ValueError("page_size and max_pages must be between 1 and 1000")
        if direction not in {"to", "from"}:
            raise ValueError("relation direction must be to or from")
        entries: dict[str, dict[str, Any]] = {}
        token = page_token or ""
        pages = 0
        partial_reason = ""
        provider_partial = False
        visited: set[str] = set()
        while pages < max_pages:
            payload: dict[str, Any] = {"entryIds": [object_id], "limit": page_size, "linkDirection": direction}
            if token:
                payload["pageToken"] = token
            visited.add(token)
            try:
                raw = self.api.read("getEntriesRelations", payload)
            except Exception:  # noqa: BLE001 - preserve earlier pages when a provider read fails
                partial_reason = "relation_read_failed"
                break
            for item in relation_entries(raw):
                relation_id, _ = object_identity(item)
                if relation_id:
                    entries[relation_id] = item
            page = _unwrap(raw)
            pages += 1
            token = str(page.get("nextPageToken") or "").strip()
            if page.get("complete") is False:
                provider_partial = True
                partial_reason = "provider_relations_partial"
            if token and token in visited:
                partial_reason = "pagination_cursor_cycle"
                token = ""
                break
            if not token:
                break
        return {
            "ok": True,
            "object_id": object_id,
            "complete": not token and not partial_reason,
            "partial_reason": partial_reason or ("page_limit_reached" if token else ""),
            "provider_complete": not provider_partial,
            "page_count": pages,
            "next_page_token": token or None,
            "relations": compact_object_index(entries.values()),
        }

    def dashboard_snapshot(
        self,
        dashboard_id: str,
        *,
        branch: str = "saved",
        revision_id: str | None = None,
        reference_dashboard_id: str | None = None,
        page_size: int = 100,
        max_pages: int = 100,
        continuation: str | None = None,
        view: str = "full",
        fields: list[str] | None = None,
    ) -> dict[str, Any]:
        _validate_view(view, fields)
        if not 1 <= page_size <= 1000 or not 1 <= max_pages <= 1000:
            raise ValueError("page_size and max_pages must be between 1 and 1000")
        binding = [dashboard_id, branch, revision_id, reference_dashboard_id, view, fields]
        state = _continuation_state(continuation, binding)
        target = self.object_get("dashboard", dashboard_id, branch=branch, revision_id=revision_id)
        reasons = list(state.get("reasons", []))
        target_revision = target["identity"]["revision_id"]
        if continuation and state["target_revision"] != target_revision:
            reasons.append("target_revision_drift")
        if target["object"].get("complete") is False:
            reasons.append("target_partial")
        relation_result = self.object_relations(
            dashboard_id, page_size=page_size, max_pages=max_pages, page_token=state.get("token")
        )
        seen = dict(state.get("seen", {}))
        unresolved = list(state.get("unresolved", []))
        dependencies: list[dict[str, Any]] = []
        new_relations: list[dict[str, Any]] = []
        for relation in relation_result["relations"]:
            object_id = str(relation["id"])
            normalized_type = object_identity(relation)[1]
            if object_id in seen:
                if seen[object_id] != normalized_type:
                    reasons.append("dependency_graph_drift")
                continue
            seen[object_id] = normalized_type
            new_relations.append(relation)
            if object_id == dashboard_id:
                continue  # The target is already read; self/cyclic edges add no dependency.
            if normalized_type not in {
                "connection",
                "dataset",
                "wizard_chart",
                "editor_chart",
                "ql_chart",
                "dashboard",
            }:
                unresolved.append({**relation, "reason": "unknown_type"})
                continue
            try:
                dependency = self.object_get(normalized_type, object_id, branch=branch)
            except Exception:  # noqa: BLE001 - failed dependencies must remain explicitly unresolved
                unresolved.append({**relation, "reason": "dependency_read_failed"})
                continue
            if dependency["object"].get("complete") is False:
                unresolved.append({**relation, "reason": "dependency_partial"})
            dependencies.append(_read_view(dependency, view=view, fields=fields, branch=branch))
        if unresolved:
            reasons.append("unresolved_dependencies")
        reference = None
        if reference_dashboard_id:
            try:
                reference = self.object_get("dashboard", reference_dashboard_id, branch=branch)
            except Exception:  # noqa: BLE001 - preserve target/dependencies when the optional reference fails
                reasons.append("reference_read_failed")
                reference = {
                    "ok": False,
                    "complete": False,
                    "partial_reason": "reference_read_failed",
                    "requested_identity": {
                        "object_type": "dashboard",
                        "object_id": reference_dashboard_id,
                        "branch": branch,
                    },
                }
            else:
                reference_complete = reference["object"].get("complete") is not False
                reference = _read_view(reference, view=view, fields=fields, branch=branch)
                reference["complete"] = reference_complete
                if not reference_complete:
                    reasons.append("reference_partial")
        if not relation_result["provider_complete"]:
            reasons.append("provider_relations_partial")
        persistent_reasons = sorted(set(reasons))
        if not relation_result["complete"] and relation_result["partial_reason"] not in reasons:
            reasons.append(relation_result["partial_reason"])
        token = relation_result["next_page_token"]
        cursor = None
        consumed_tokens = list(state.get("consumed_tokens", []))
        if relation_result["page_count"]:
            consumed_tokens.append(state.get("token", ""))
        if token and token in consumed_tokens:
            reasons.append("pagination_cursor_cycle")
            token = None
        if token:
            cursor = _encode_continuation(
                {
                    "binding": binding,
                    "token": token,
                    "target_revision": state.get("target_revision", target_revision),
                    "seen": seen,
                    "unresolved": unresolved,
                    "reasons": persistent_reasons,
                    "consumed_tokens": consumed_tokens,
                }
            )
        result: dict[str, Any] = {
            "ok": True,
            "complete": not reasons,
            "partial_reason": reasons[0] if reasons else "",
            "partial_reasons": sorted(set(reasons)),
            "continuation": cursor,
            "result_scope": "incremental_page" if continuation else "initial_pages",
            "graph_consistency": "drift_detected" if any("drift" in reason for reason in reasons) else "unverified",
            "consistency_note": "Provider relation pagination has no snapshot version; membership and dependency revisions across pages are not proven stable.",
            "target": _read_view(target, view=view, fields=fields, branch=branch),
            "relations": new_relations,
            "relation_scan": {key: value for key, value in relation_result.items() if key != "relations"},
            "dependencies": dependencies,
            "unresolved_relations": unresolved,
        }
        if reference is not None:
            result["reference"] = reference
        return result


def _validate_view(view: str, fields: list[str] | None) -> None:
    if view not in {"full", "summary", "projection"}:
        raise ValueError("view must be full, summary or projection")
    if view == "projection":
        if not fields or any(
            not isinstance(path, str) or not path.startswith("/") or re.search(r"~(?![01])", path) for path in fields
        ):
            raise ValueError("projection requires fields as nonempty JSON pointers, for example /data/name")
    elif fields is not None:
        raise ValueError("fields requires view=projection")


def _read_view(result: dict[str, Any], *, view: str, fields: list[str] | None, branch: str) -> dict[str, Any]:
    if view == "full":
        return result
    payload = result["object"]
    identity = result["identity"]
    projected: dict[str, Any] = {}
    missing: list[str] = []
    for path in fields or []:
        value: Any = payload
        try:
            for key in path[1:].split("/"):
                key = key.replace("~1", "/").replace("~0", "~")
                if isinstance(value, list):
                    if not re.fullmatch(r"0|[1-9][0-9]*", key):
                        raise KeyError(key)
                    value = value[int(key)]
                else:
                    value = value[key]
            projected[path] = value
        except (KeyError, IndexError, TypeError, ValueError):
            missing.append(path)
    return {
        "ok": result["ok"],
        "identity": identity,
        "read_view": view,
        "full_state": False,
        "complete": payload.get("complete") is not False,
        "projection": fields or [],
        "missing_fields": missing,
        "summary": {"top_level_fields": sorted(payload), "field_count": len(payload)},
        "object": projected,
        "full_read": {
            "tool": "dl_object_get",
            "arguments": {
                "object_type": identity["object_type"],
                "object_id": identity["object_id"],
                "branch": branch,
                "revision_id": identity["revision_id"],
            },
        },
    }


def _encode_continuation(state: dict[str, Any]) -> str:
    return base64.urlsafe_b64encode(json.dumps(state, separators=(",", ":")).encode()).decode()


def _continuation_state(cursor: str | None, binding: list[Any]) -> dict[str, Any]:
    if cursor is None:
        return {}
    try:
        state = json.loads(base64.b64decode(cursor, altchars=b"-_", validate=True))
        if not isinstance(state, dict) or state.get("binding") != binding:
            raise ValueError("scope mismatch")
        if not isinstance(state.get("seen"), dict) or not isinstance(state.get("unresolved"), list):
            raise TypeError("invalid state")
        if not isinstance(state.get("token"), str) or not isinstance(state.get("reasons"), list):
            raise TypeError("invalid state")
        if "target_revision" not in state:
            raise ValueError("missing target revision")
        return state
    except (ValueError, TypeError, UnicodeError) as exc:
        raise ValueError("invalid continuation or target/branch/revision/view mismatch; restart the snapshot") from exc


def _revision_id(payload: Mapping[str, Any], *, branch: str, fallback: str | None) -> str:
    branch_keys = (
        ("published_id", "publishedId", "saved_id", "savedId")
        if branch == "published"
        else ("saved_id", "savedId", "published_id", "publishedId")
    )
    containers: list[Mapping[str, Any]] = [payload]
    entry = payload.get("entry")
    if isinstance(entry, Mapping):
        containers.append(entry)
    for container in containers:
        for key in ("rev_id", "revId", *branch_keys):
            value = container.get(key)
            if isinstance(value, str) and value:
                return value
    return fallback or ""


def _unwrap(raw: Mapping[str, Any]) -> Mapping[str, Any]:
    value = raw
    while isinstance(value.get("result"), Mapping):
        value = value["result"]
    if isinstance(value.get("response"), Mapping):
        value = value["response"]
    return value
