from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from typing import Any, Protocol
from uuid import uuid4

from datalens_dev_mcp.api.errors import (
    DataLensApiError,
    InputContractError,
    UncertainWriteError,
    error_response,
    safe_error_text,
)
from datalens_dev_mcp.authoring.artifacts import resolve_artifact
from datalens_dev_mcp.objects.relations import object_identity
from datalens_dev_mcp.operation_store import OperationStore

_EDITOR_ARTIFACT_TYPES = frozenset(
    {
        "editor_chart",
        "advanced-chart_node",
        "advanced_chart",
        "table_node",
        "d3_node",
        "markdown_node",
        "control_node",
    }
)
_EDITOR_ARTIFACT_TABS = {
    "meta.json": "meta",
    "params.js": "params",
    "sources.js": "sources",
    "prepare.js": "prepare",
    "controls.js": "controls",
    "config.js": "config",
}


class MutationBackend(Protocol):
    def create(self, draft: dict[str, Any], destination: dict[str, Any]) -> dict[str, Any]: ...
    def update(self, object_type: str, object_id: str, snapshot: dict[str, Any]) -> dict[str, Any]: ...
    def publish(self, object_type: str, object_id: str, saved: dict[str, Any]) -> dict[str, Any]: ...


class ObjectReader(Protocol):
    def object_get(
        self, object_type: str, object_id: str, *, branch: str = "saved", revision_id: str | None = None
    ) -> dict[str, Any]: ...


def semantic_merge(base: Any, patch: Any) -> Any:
    """Merge mappings narrowly; lists are intentional atomic values."""
    if isinstance(base, dict) and isinstance(patch, dict):
        result = deepcopy(base)
        for key, value in patch.items():
            result[key] = semantic_merge(base.get(key), value) if key in base else deepcopy(value)
        return result
    return deepcopy(patch)


def semantic_diff(current: Any, proposed: Any, path: str = "") -> list[dict[str, Any]]:
    if isinstance(current, dict) and isinstance(proposed, dict):
        changes: list[dict[str, Any]] = []
        for key in sorted(set(current) | set(proposed)):
            child = f"{path}/{key.replace('~', '~0').replace('/', '~1')}"
            if key not in current:
                changes.append({"path": child, "before": None, "after": deepcopy(proposed[key])})
            elif key not in proposed:
                changes.append({"path": child, "before": deepcopy(current[key]), "after": None})
            else:
                changes.extend(semantic_diff(current[key], proposed[key], child))
        return changes
    return (
        [] if current == proposed else [{"path": path or "/", "before": deepcopy(current), "after": deepcopy(proposed)}]
    )


class ObjectMutationService:
    def __init__(self, *, reader: ObjectReader, backend: MutationBackend, store: OperationStore | None = None) -> None:
        self.reader = reader
        self.backend = backend
        self.store = store or OperationStore()

    def diff(self, object_type: str, object_id: str, patch: dict[str, Any]) -> dict[str, Any]:
        current = self.reader.object_get(object_type, object_id, branch="saved")
        proposed = semantic_merge(current["object"], patch)
        return {
            "ok": True,
            "identity": current["identity"],
            "changes": semantic_diff(current["object"], proposed),
            "proposed": proposed,
        }

    def create_objects(
        self,
        drafts: list[dict[str, Any]],
        destination: dict[str, Any],
        *,
        delivery_mode: str = "save",
        operation_id: str | None = None,
    ) -> dict[str, Any]:
        if delivery_mode != "save":
            raise InputContractError("create delivery_mode must be 'save'; publish is an explicit later operation")
        from datalens_dev_mcp.dashboard.composition import bind_object_references, dependency_order

        try:
            drafts = dependency_order([resolve_artifact(draft) for draft in drafts])
        except (ValueError, TypeError) as exc:
            raise InputContractError(safe_error_text(exc)) from exc
        admitted, record = self._record("create", {"drafts": drafts, "destination": destination}, operation_id)
        if not admitted:
            return record
        items = self._items(record, drafts, lambda d, i: str(d.get("client_ref") or f"create-{i}"))
        for index, draft in enumerate(drafts):
            item = items[index]
            if item.get("status") in {"completed", "uncertain"}:
                continue
            by_key = {row["key"]: row for row in items}
            if any(by_key[dep]["status"] != "completed" for dep in draft.get("depends_on", [])):
                item.update(status="pending", code="dependency_not_completed")
                self._save(record)
                continue
            try:
                ids = {
                    key: row["target"]["object_id"]
                    for key, row in by_key.items()
                    if row["status"] == "completed" and row.get("target")
                }
                draft = bind_object_references(draft, ids)
                item["desired"] = _recordable(draft.get("snapshot") or draft.get("draft") or {})
                self._begin(record, item)
                response = self.backend.create(draft, destination)
                object_id = str(response.get("object_id") or response.get("id") or "")
                if not object_id:
                    raise UncertainWriteError("create returned no object id")
                item["target"] = {"object_type": str(draft["object_type"]), "object_id": object_id}
                if isinstance(response.get("expected_readback"), dict):
                    item["desired"] = _recordable(response["expected_readback"])
                self._returned(record, item, response)
                self._verify_readback(item, branch="saved")
            except UncertainWriteError as exc:
                self._failure(item, exc)
            except (DataLensApiError, ValueError, TypeError) as exc:
                self._failure(item, exc)
            self._save(record)
        return self._save(record)

    def update_objects(
        self, changes: list[dict[str, Any]], *, delivery_mode: str = "save", operation_id: str | None = None
    ) -> dict[str, Any]:
        if delivery_mode != "save":
            raise InputContractError("update delivery_mode must be 'save'; publish is an explicit later operation")
        try:
            changes = [_resolve_update_change(change) for change in changes]
        except (ValueError, TypeError) as exc:
            raise InputContractError(safe_error_text(exc)) from exc
        admitted, record = self._record("update", {"changes": changes}, operation_id)
        if not admitted:
            return record
        items = self._items(record, changes, lambda c, i: f"{c.get('object_type')}:{c.get('object_id')}")
        for index, change in enumerate(changes):
            item = items[index]
            if item.get("status") in {"completed", "uncertain", "blocked"}:
                continue
            object_type, object_id = str(change["object_type"]), str(change["object_id"])
            try:
                current = self.reader.object_get(object_type, object_id, branch="saved")
                if not _usable_full_read(current):
                    item.update(
                        status="blocked",
                        code="full_read_required",
                        next_action="Read a complete full saved target before preparing replacement.",
                    )
                    self._save(record)
                    continue
                actual_revision = str(current.get("identity", {}).get("revision_id") or "")
                expected = str(change.get("expected_revision") or "")
                if expected and actual_revision != expected:
                    item.update(
                        status="blocked",
                        code="revision_changed",
                        expected_revision=expected,
                        observed_revision=actual_revision,
                    )
                    self._save(record)
                    continue
                patch = deepcopy(change.get("patch") or {})
                proposed = semantic_merge(current["object"], patch)
                item.update(
                    target={"object_type": object_type, "object_id": object_id},
                    desired=_recordable(patch),
                    expected_revision=actual_revision or None,
                    changes=semantic_diff(current["object"], proposed),
                )
                self._begin(record, item)
                response = self.backend.update(object_type, object_id, proposed)
                self._returned(record, item, response)
                self._verify_readback(item, branch="saved")
            except UncertainWriteError as exc:
                self._failure(item, exc)
            except (DataLensApiError, ValueError, TypeError) as exc:
                self._failure(item, exc)
            self._save(record)
        return self._save(record)

    def publish_objects(self, targets: list[dict[str, Any]], *, operation_id: str | None = None) -> dict[str, Any]:
        admitted, record = self._record("publish", {"targets": targets}, operation_id)
        if not admitted:
            return record
        items = self._items(record, targets, lambda t, i: f"{t.get('object_type')}:{t.get('object_id')}")
        for index, target in enumerate(targets):
            item = items[index]
            if item.get("status") in {"completed", "uncertain", "blocked"}:
                continue
            object_type, object_id = str(target["object_type"]), str(target["object_id"])
            if object_type in {"dataset", "connection", "workbook"}:
                item.update(status="blocked", code="object_has_no_publish_branch")
                self._save(record)
                continue
            try:
                saved = self.reader.object_get(object_type, object_id, branch="saved")
                if not _usable_full_read(saved):
                    item.update(
                        status="blocked",
                        code="full_read_required",
                        next_action="Read a complete full saved target before publishing.",
                    )
                    self._save(record)
                    continue
                observed = str(saved.get("identity", {}).get("revision_id") or "")
                expected = str(target.get("expected_saved_revision") or "")
                if not observed:
                    item.update(status="blocked", code="saved_revision_missing")
                    self._save(record)
                    continue
                if expected and observed != expected:
                    item.update(
                        status="blocked",
                        code="revision_changed",
                        expected_revision=expected,
                        observed_revision=observed,
                    )
                    self._save(record)
                    continue
                item.update(
                    target={"object_type": object_type, "object_id": object_id},
                    expected_revision=observed or None,
                    desired=_recordable(_publish_content(saved["object"])),
                )
                if object_type in {"dashboard", "wizard_chart", "html_page"}:
                    item["required_published_revision"] = observed
                self._begin(record, item)
                response = self.backend.publish(object_type, object_id, saved)
                self._returned(record, item, response)
                self._verify_readback(item, branch="published")
            except UncertainWriteError as exc:
                self._failure(item, exc)
            except (DataLensApiError, ValueError, TypeError) as exc:
                self._failure(item, exc)
            self._save(record)
        return self._save(record)

    def get_operation(self, operation_id: str) -> dict[str, Any]:
        value = self.store.get(operation_id)
        if value is None:
            return {"ok": False, "status": "not_found", "operation_id": operation_id}
        return value

    def reconcile(self, operation_id: str) -> dict[str, Any]:
        record = self.store.get(operation_id)
        if record is None:
            return {"ok": False, "status": "not_found", "operation_id": operation_id, "write_replayed": False}
        for item in record.get("results", []):
            if item.get("status") != "uncertain":
                continue
            target = item.get("target") or {}
            object_type, object_id = str(target.get("object_type") or ""), str(target.get("object_id") or "")
            if not object_type or not object_id:
                item["code"] = "identity_lookup_unavailable"
                continue
            branch = "published" if record.get("effect") == "publish" else "saved"
            try:
                self._verify_readback(item, branch=branch)
                if item["status"] == "completed":
                    item["code"] = "reconciled_applied"
            except (DataLensApiError, ValueError, TypeError) as exc:
                item.update(status="uncertain", code="readback_unavailable", error=safe_error_text(exc))
        result = self._save(record)
        result["write_replayed"] = False
        return result

    def _begin(self, record: dict[str, Any], item: dict[str, Any]) -> None:
        # Persist before crossing the network boundary. A killed process cannot
        # subsequently mistake an in-flight mutation for an unattempted one.
        item.update(
            status="uncertain",
            code="write_outcome_unknown",
            write_returned=False,
            next_action="Inspect this operation_id and reconcile exact target readback; do not replay the write.",
        )
        item.pop("error", None)
        self._save(record)

    def _returned(self, record: dict[str, Any], item: dict[str, Any], response: dict[str, Any]) -> None:
        item.update(write_returned=True, code="readback_pending")
        value = response.get("object") or {}
        item["returned_revision"] = value.get("revId") or value.get("rev_id")
        self._save(record)

    def _verify_readback(self, item: dict[str, Any], *, branch: str) -> None:
        target = item["target"]
        readback = self.reader.object_get(target["object_type"], target["object_id"], branch=branch)
        item["readback"] = _recordable(readback)
        identity = readback.get("identity") or {}
        allowed_branch = "unbranched" if target["object_type"] in {"dataset", "connection", "workbook"} else branch
        correct_identity = (
            identity.get("object_id") == target["object_id"]
            and identity.get("object_type") == target["object_type"]
            and identity.get("branch") == allowed_branch
        )
        payload = readback.get("object") or {}
        payload_id, _ = object_identity(payload)
        correct_identity = correct_identity and (not payload_id or payload_id == target["object_id"])
        desired = item.get("desired") or {}
        content_matches = _readback_contains(
            readback.get("object") or {}, _readback_intent(target["object_type"], desired)
        )
        returned_revision = item.get("returned_revision")
        # Some official SDK update builders return their pre-write target
        # snapshot even though the provider has already advanced the object.
        # That revision is evidence about the input precondition, not the
        # resulting revision. A different third revision still remains
        # ambiguous and must not be accepted or replayed.
        revision_matches = not returned_revision or returned_revision in {
            identity.get("revision_id"),
            item.get("expected_revision"),
        }
        required_revision = item.get("required_published_revision")
        if required_revision and identity.get("revision_id") != required_revision:
            revision_matches = False
        if _usable_full_read(readback) and correct_identity and content_matches and revision_matches:
            item.update(status="completed", code="readback_verified", observed_revision=identity.get("revision_id"))
            item.pop("error", None)
            item.pop("next_action", None)
        else:
            # An old or different snapshot cannot prove rejection: the write
            # may still be in flight, or a later edit may have superseded it.
            item.update(
                status="uncertain",
                code="readback_mismatch",
                next_action="Reconcile exact target identity, branch and business content; do not replay the write.",
            )

    @staticmethod
    def _failure(item: dict[str, Any], exc: Exception) -> None:
        effect_possible = item.get("status") == "uncertain" or bool(item.get("write_returned"))
        # A rejection during readback cannot undo an already returned write.
        detail = error_response(exc, effect_possible=effect_possible)
        uncertain = bool(item.get("write_returned")) or detail["code"] == "write_outcome_unknown"
        if uncertain:
            detail = error_response(UncertainWriteError(safe_error_text(exc)))
        item.update(
            status="uncertain" if uncertain else "failed",
            error=detail["error"],
            code=detail["code"],
            next_action=detail["next_action"],
        )

    def _record(self, effect: str, request: dict[str, Any], operation_id: str | None) -> tuple[bool, dict[str, Any]]:
        oid = operation_id or str(uuid4())
        try:
            digest = _digest(request)
        except (ValueError, TypeError) as exc:
            raise InputContractError(safe_error_text(exc)) from exc
        return self.store.claim(
            {
                "ok": False,
                "operation_id": oid,
                "effect": effect,
                "request_digest": digest,
                "status": "pending",
                "next_action": "Inspect the existing receipt; an active or interrupted claim must not be replayed.",
                "results": [],
            }
        )

    @staticmethod
    def _items(record: dict[str, Any], values: list[dict[str, Any]], key_fn: Any) -> list[dict[str, Any]]:
        if not record["results"]:
            record["results"] = [
                {"key": key_fn(value, index), "status": "pending"} for index, value in enumerate(values)
            ]
        if len(record["results"]) != len(values):
            raise ValueError("operation item count changed")
        return record["results"]

    def _save(self, record: dict[str, Any]) -> dict[str, Any]:
        statuses = [str(item.get("status") or "pending") for item in record.get("results", [])]
        if any(value == "uncertain" for value in statuses):
            status = "uncertain"
        elif any(value == "blocked" for value in statuses):
            status = "blocked"
        elif any(value == "failed" for value in statuses):
            status = "partial" if any(value == "completed" for value in statuses) else "failed"
        elif statuses and all(value == "completed" for value in statuses):
            status = "completed"
        else:
            status = "pending"
        record["status"] = status
        record["ok"] = status == "completed"
        if status == "completed":
            record.pop("next_action", None)
        try:
            return self.store.put(record)
        except OSError as exc:
            if any(
                item.get("status") == "uncertain" or item.get("write_returned") for item in record.get("results", [])
            ):
                raise UncertainWriteError(
                    "operation persistence failed; inspect the durable receipt and reconcile"
                ) from exc
            raise


def _resolve_update_change(change: dict[str, Any]) -> dict[str, Any]:
    patch = change.get("patch")
    if isinstance(patch, dict) and (patch.get("full_state") is False or patch.get("read_view", "full") != "full"):
        raise InputContractError(
            "replacement requires fresh full state; summary/projection envelopes are not write payloads"
        )
    if "artifact_path" not in change:
        return deepcopy(change)
    allowed = {"artifact_path", "object_type", "object_id", "expected_revision"}
    if set(change) - allowed:
        raise InputContractError(
            "artifact updates allow only artifact_path, object_type, object_id and expected_revision"
        )
    object_type, object_id = change.get("object_type"), change.get("object_id")
    if not isinstance(object_type, str) or not object_type or not isinstance(object_id, str) or not object_id:
        raise InputContractError("artifact update requires nonempty object_type and object_id")
    draft = resolve_artifact({"artifact_path": change["artifact_path"]})
    if object_type not in _EDITOR_ARTIFACT_TYPES or draft.get("object_type") not in _EDITOR_ARTIFACT_TYPES:
        raise InputContractError("artifact update currently supports compiled Editor drafts only")
    tabs = draft.get("tabs")
    if not isinstance(tabs, dict) or not tabs:
        raise InputContractError("compiled Editor artifact requires nonempty tabs")
    data: dict[str, str] = {}
    for filename, content in tabs.items():
        key = _EDITOR_ARTIFACT_TABS.get(filename)
        if key is None or not isinstance(content, str):
            raise InputContractError(f"unsupported compiled Editor tab: {filename}")
        data[key] = content
    patch: dict[str, Any] = {"data": data}
    if isinstance(draft.get("name"), str) and draft["name"]:
        patch["name"] = draft["name"]
    return {
        "object_type": object_type,
        "object_id": object_id,
        "expected_revision": change.get("expected_revision"),
        "patch": patch,
    }


def _digest(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _contains(actual: Any, expected: Any) -> bool:
    if isinstance(expected, dict):
        return isinstance(actual, dict) and all(
            key in actual and _contains(actual[key], value) for key, value in expected.items()
        )
    return actual == expected


def _usable_full_read(readback: dict[str, Any]) -> bool:
    """Only complete full provider state may authorize replacement or prove it."""
    payload = readback.get("object")
    if readback.get("ok") is not True or not isinstance(payload, dict):
        return False
    return all(
        value.get("ok") is not False
        and value.get("complete") is not False
        and value.get("full_state") is not False
        and value.get("read_view", "full") == "full"
        for value in (readback, payload)
    )


def _readback_intent(object_type: str, desired: dict[str, Any]) -> dict[str, Any]:
    intent = deepcopy(desired)
    if object_type == "dataset":
        # Exact provider-owned preconditions, not recursive business-field filtering.
        intent.pop("revId", None)
        intent.pop("rev_id", None)
        dataset = intent.get("dataset")
        if isinstance(dataset, dict):
            dataset.pop("revision_id", None)
    return intent


def _readback_contains(actual: Any, expected: Any) -> bool:
    if not isinstance(expected, dict) or "name" not in expected:
        return _contains(actual, expected)
    if not isinstance(actual, dict):
        return False
    actual_name = actual.get("name")
    entry = actual.get("entry")
    if actual_name is None and isinstance(entry, dict):
        actual_name = entry.get("name")
        key = entry.get("key")
        if actual_name is None and isinstance(key, str):
            actual_name = key.rsplit("/", 1)[-1]
    if actual_name != expected["name"]:
        return False
    return _contains(actual, {key: value for key, value in expected.items() if key != "name"})


def _publish_content(snapshot: dict[str, Any]) -> dict[str, Any]:
    # Response identity/audit fields do not belong to the mutable document.
    entry = snapshot.get("entry")
    if isinstance(entry, dict):
        return {"entry": _publish_content(entry)}
    keys = ("data", "meta", "annotation", "content")
    content = {key: deepcopy(snapshot[key]) for key in keys if key in snapshot}
    if not content:
        raise ValueError("saved readback lacks publishable content")
    return content


_SENSITIVE_KEY_PARTS = ("password", "secret", "token", "credential", "authorization", "cookie")


def _recordable(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: _recordable(item)
            for key, item in value.items()
            if not any(part in str(key).lower() for part in _SENSITIVE_KEY_PARTS)
        }
    if isinstance(value, list):
        return [_recordable(item) for item in value]
    return deepcopy(value)


def default_mutation_service() -> ObjectMutationService:
    from datalens_dev_mcp.api.runtime import get_runtime
    from datalens_dev_mcp.objects.read import ObjectReadService

    runtime = get_runtime()
    return ObjectMutationService(
        reader=ObjectReadService(api=runtime.api, sdk=runtime.sdk),
        backend=runtime.sdk,
    )


def create_objects(
    drafts: list[dict[str, Any]],
    destination: dict[str, Any],
    delivery_mode: str = "save",
    operation_id: str | None = None,
    *,
    include_detail: bool = False,
) -> dict[str, Any]:
    from datalens_dev_mcp.operation_store import compact_operation

    result = default_mutation_service().create_objects(
        drafts, destination, delivery_mode=delivery_mode, operation_id=operation_id
    )
    return result if include_detail else compact_operation(result)


def update_objects(
    changes: list[dict[str, Any]],
    delivery_mode: str = "save",
    operation_id: str | None = None,
    *,
    include_detail: bool = False,
) -> dict[str, Any]:
    from datalens_dev_mcp.operation_store import compact_operation

    result = default_mutation_service().update_objects(changes, delivery_mode=delivery_mode, operation_id=operation_id)
    return result if include_detail else compact_operation(result)
