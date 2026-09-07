from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from typing import Any, Protocol
from uuid import uuid4

from datalens_dev_mcp.api.errors import DataLensApiError, UncertainWriteError, safe_error_text
from datalens_dev_mcp.operation_store import OperationStore
from datalens_dev_mcp.authoring.artifacts import resolve_artifact


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
    return [] if current == proposed else [{"path": path or "/", "before": deepcopy(current), "after": deepcopy(proposed)}]


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
            raise ValueError("create delivery_mode must be 'save'; publish is an explicit later operation")
        from datalens_dev_mcp.dashboard.composition import dependency_order

        drafts = dependency_order([resolve_artifact(draft) for draft in drafts])
        _, record = self._record("create", {"drafts": drafts, "destination": destination}, operation_id)
        if record.get("status") == "completed":
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
                item["desired"] = deepcopy(draft.get("snapshot") or draft.get("draft") or {})
                self._begin(record, item)
                response = self.backend.create(draft, destination)
                object_id = str(response.get("object_id") or response.get("id") or "")
                if not object_id:
                    raise UncertainWriteError("create returned no object id")
                item["target"] = {"object_type": str(draft["object_type"]), "object_id": object_id}
                if isinstance(response.get("expected_readback"), dict):
                    item["desired"] = deepcopy(response["expected_readback"])
                self._returned(record, item, response)
                self._verify_readback(item, branch="saved")
            except UncertainWriteError as exc:
                item.update(status="uncertain", error=safe_error_text(exc), code="write_outcome_unknown")
            except (DataLensApiError, ValueError, TypeError) as exc:
                self._failure(item, exc)
            self._save(record)
        return self._save(record)

    def update_objects(
        self, changes: list[dict[str, Any]], *, delivery_mode: str = "save", operation_id: str | None = None
    ) -> dict[str, Any]:
        if delivery_mode != "save":
            raise ValueError("update delivery_mode must be 'save'; publish is an explicit later operation")
        changes = [resolve_artifact(change) for change in changes]
        _, record = self._record("update", {"changes": changes}, operation_id)
        if record.get("status") == "completed":
            return record
        items = self._items(record, changes, lambda c, i: f"{c.get('object_type')}:{c.get('object_id')}")
        for index, change in enumerate(changes):
            item = items[index]
            if item.get("status") in {"completed", "uncertain", "blocked"}:
                continue
            object_type, object_id = str(change["object_type"]), str(change["object_id"])
            try:
                current = self.reader.object_get(object_type, object_id, branch="saved")
                actual_revision = str(current.get("identity", {}).get("revision_id") or "")
                expected = str(change.get("expected_revision") or "")
                if expected and actual_revision != expected:
                    item.update(
                        status="blocked", code="revision_changed", expected_revision=expected, observed_revision=actual_revision
                    )
                    self._save(record)
                    continue
                patch = deepcopy(change.get("patch") or {})
                proposed = semantic_merge(current["object"], patch)
                item.update(
                    target={"object_type": object_type, "object_id": object_id},
                    desired=patch,
                    expected_revision=actual_revision or None,
                    changes=semantic_diff(current["object"], proposed),
                )
                self._begin(record, item)
                response = self.backend.update(object_type, object_id, proposed)
                self._returned(record, item, response)
                self._verify_readback(item, branch="saved")
            except UncertainWriteError as exc:
                item.update(status="uncertain", error=safe_error_text(exc), code="write_outcome_unknown")
            except (DataLensApiError, ValueError, TypeError) as exc:
                self._failure(item, exc)
            self._save(record)
        return self._save(record)

    def publish_objects(self, targets: list[dict[str, Any]], *, operation_id: str | None = None) -> dict[str, Any]:
        _, record = self._record("publish", {"targets": targets}, operation_id)
        if record.get("status") == "completed":
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
                observed = str(saved.get("identity", {}).get("revision_id") or "")
                expected = str(target.get("expected_saved_revision") or "")
                if not observed:
                    item.update(status="blocked", code="saved_revision_missing")
                    self._save(record)
                    continue
                if expected and observed != expected:
                    item.update(status="blocked", code="revision_changed", expected_revision=expected, observed_revision=observed)
                    self._save(record)
                    continue
                item.update(
                    target={"object_type": object_type, "object_id": object_id},
                    expected_revision=observed or None,
                    desired=_publish_content(saved["object"]),
                )
                self._begin(record, item)
                response = self.backend.publish(object_type, object_id, saved)
                self._returned(record, item, response)
                self._verify_readback(item, branch="published")
            except UncertainWriteError as exc:
                item.update(status="uncertain", error=safe_error_text(exc), code="write_outcome_unknown")
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
        item.update(status="uncertain", code="write_outcome_unknown", write_returned=False)
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
        item["readback"] = readback
        identity = readback.get("identity") or {}
        allowed_branch = "unbranched" if target["object_type"] in {"dataset", "connection", "workbook"} else branch
        correct_identity = (
            identity.get("object_id") == target["object_id"]
            and identity.get("object_type") == target["object_type"]
            and identity.get("branch") == allowed_branch
        )
        desired = item.get("desired") or {}
        content_matches = _contains(readback.get("object") or {}, desired)
        returned_revision = item.get("returned_revision")
        revision_matches = not returned_revision or returned_revision == identity.get("revision_id")
        if readback.get("ok") and correct_identity and content_matches and revision_matches:
            item.update(status="completed", code="readback_verified", observed_revision=identity.get("revision_id"))
            item.pop("error", None)
        else:
            # An old or different snapshot cannot prove rejection: the write
            # may still be in flight, or a later edit may have superseded it.
            item.update(status="uncertain", code="readback_mismatch")

    @staticmethod
    def _failure(item: dict[str, Any], exc: Exception) -> None:
        rejected = isinstance(exc, (ValueError, TypeError)) or (
            isinstance(exc, DataLensApiError)
            and exc.response_received is True
            and exc.http_status is not None
            and 400 <= exc.http_status < 500
            and exc.http_status not in {408, 409}
        )
        uncertain = item.get("write_returned") or (item.get("status") == "uncertain" and not rejected)
        item.update(
            status="uncertain" if uncertain else "failed",
            error=safe_error_text(exc),
            code="write_outcome_unknown" if uncertain else "write_failed",
        )

    def _record(self, effect: str, request: dict[str, Any], operation_id: str | None) -> tuple[str, dict[str, Any]]:
        oid = operation_id or str(uuid4())
        digest = _digest(request)
        existing = self.store.get(oid)
        if existing is not None:
            if existing.get("effect") != effect or existing.get("request_digest") != digest:
                raise ValueError("operation_id is already bound to a different request")
            return oid, existing
        return oid, {"ok": True, "operation_id": oid, "effect": effect, "request_digest": digest, "status": "pending", "results": []}

    @staticmethod
    def _items(record: dict[str, Any], values: list[dict[str, Any]], key_fn: Any) -> list[dict[str, Any]]:
        if not record["results"]:
            record["results"] = [{"key": key_fn(value, index), "status": "pending"} for index, value in enumerate(values)]
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
        return self.store.put(record)


def _digest(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _contains(actual: Any, expected: Any) -> bool:
    if isinstance(expected, dict):
        return isinstance(actual, dict) and all(key in actual and _contains(actual[key], value) for key, value in expected.items())
    return actual == expected


def _publish_content(snapshot: dict[str, Any]) -> dict[str, Any]:
    # Response identity/audit fields do not belong to the mutable document.
    keys = ("data", "meta", "annotation", "content")
    content = {key: deepcopy(snapshot[key]) for key in keys if key in snapshot}
    if not content:
        raise ValueError("saved readback lacks publishable content")
    return content


def default_mutation_service() -> ObjectMutationService:
    from datalens_dev_mcp.api.client import DataLensApiClient
    from datalens_dev_mcp.api.sdk_adapter import SdkAdapter
    from datalens_dev_mcp.config import DataLensConfig
    from datalens_dev_mcp.objects.read import ObjectReadService

    config = DataLensConfig.from_env()
    sdk = SdkAdapter(config)
    return ObjectMutationService(reader=ObjectReadService(api=DataLensApiClient(config), sdk=sdk), backend=sdk)


def create_objects(
    drafts: list[dict[str, Any]],
    destination: dict[str, Any],
    delivery_mode: str = "save",
    operation_id: str | None = None,
) -> dict[str, Any]:
    return default_mutation_service().create_objects(
        drafts, destination, delivery_mode=delivery_mode, operation_id=operation_id
    )


def update_objects(
    changes: list[dict[str, Any]], delivery_mode: str = "save", operation_id: str | None = None
) -> dict[str, Any]:
    return default_mutation_service().update_objects(changes, delivery_mode=delivery_mode, operation_id=operation_id)
