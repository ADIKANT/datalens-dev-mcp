from __future__ import annotations

import hashlib
import json
from collections import deque
from typing import Any

from datalens_dev_mcp.api.errors import DataLensApiError, safe_error_text


def _key(item: dict[str, Any]) -> tuple[str, str]:
    return str(item["object_type"]), str(item["object_id"])


class CleanupService:
    def __init__(self, *, reader: Any, deleter: Any) -> None:
        self.reader = reader
        self.deleter = deleter

    def preview(
        self, candidates: list[dict[str, Any]], *, preserve_roots: list[dict[str, Any]]
    ) -> dict[str, Any]:
        normalized = [{"object_type": _key(item)[0], "object_id": _key(item)[1]} for item in candidates]
        by_id = {item["object_id"]: item for item in normalized}
        preserve: set[tuple[str, str]] = set()
        queue = deque({"object_type": _key(item)[0], "object_id": _key(item)[1]} for item in preserve_roots)
        complete = True
        while queue:
            item = queue.popleft()
            key = _key(item)
            if key in preserve:
                continue
            preserve.add(key)
            try:
                relations = self.reader.object_relations(item["object_id"])
                complete = complete and bool(relations.get("complete", False))
                for relation in relations.get("relations") or []:
                    related = {"object_type": str(relation.get("type") or ""), "object_id": str(relation.get("id") or "")}
                    if related["object_id"] in by_id:
                        related = by_id[related["object_id"]]
                        queue.append(related)
            except (DataLensApiError, ValueError, TypeError):
                complete = False
        keep = [item for item in normalized if _key(item) in preserve]
        delete = [item for item in normalized if _key(item) not in preserve]
        body = {"complete": complete, "preserve": keep, "delete": delete}
        return {"ok": complete, **body, "preview_digest": _digest(body)}

    def apply(self, preview: dict[str, Any], *, confirmed_delete: list[dict[str, Any]]) -> dict[str, Any]:
        expected = [{"object_type": _key(item)[0], "object_id": _key(item)[1]} for item in preview.get("delete") or []]
        confirmed = [{"object_type": _key(item)[0], "object_id": _key(item)[1]} for item in confirmed_delete]
        if confirmed != expected:
            raise ValueError("confirmed_delete must exactly match the ordered cleanup preview")
        body = {"complete": bool(preview.get("complete")), "preserve": preview.get("preserve") or [], "delete": expected}
        if preview.get("preview_digest") != _digest(body):
            raise ValueError("cleanup preview digest does not match its contents")
        results: list[dict[str, Any]] = []
        for item in expected:
            try:
                self.deleter.delete(item["object_type"], item["object_id"])
                results.append({**item, "status": "deleted"})
            except DataLensApiError as exc:
                if exc.http_status == 404:
                    results.append({**item, "status": "already_absent"})
                else:
                    results.append({**item, "status": "failed", "error": safe_error_text(exc)})
        failed = any(item["status"] == "failed" for item in results)
        absent = any(item["status"] == "already_absent" for item in results)
        return {"ok": not failed, "status": "failed" if failed else "completed_with_absent" if absent else "completed", "results": results}


def _digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()

