from __future__ import annotations

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
    ) -> dict[str, Any]:
        if object_type == "html_page":
            request = {"entryId": object_id, "branch": branch}
            if revision_id:
                request["revId"] = revision_id
            payload = dict(_unwrap(self.api.read("getHtmlPage", request)))
        else:
            payload = self.sdk.get_object(object_type, object_id, branch=branch, revision_id=revision_id)
        actual_revision = _revision_id(payload, branch=branch, fallback=revision_id)
        unbranched = object_type in {"workbook", "connection", "dataset"}
        return {
            "ok": True,
            "identity": {
                "object_type": object_type,
                "object_id": object_id,
                "branch": "unbranched" if unbranched else branch,
                "revision_id": actual_revision or None,
            },
            "object": payload,
        }

    def object_relations(
        self,
        object_id: str,
        *,
        direction: str = "to",
        page_size: int = 100,
        max_pages: int = 100,
    ) -> dict[str, Any]:
        if direction not in {"to", "from"}:
            raise ValueError("relation direction must be to or from")
        entries: dict[str, dict[str, Any]] = {}
        token = ""
        pages = 0
        while pages < max_pages:
            payload: dict[str, Any] = {"entryIds": [object_id], "limit": page_size, "linkDirection": direction}
            if token:
                payload["pageToken"] = token
            raw = self.api.read("getEntriesRelations", payload)
            for item in relation_entries(raw):
                relation_id, _ = object_identity(item)
                if relation_id:
                    entries[relation_id] = item
            page = _unwrap(raw)
            pages += 1
            token = str(page.get("nextPageToken") or "").strip()
            if not token:
                break
        return {
            "ok": True,
            "object_id": object_id,
            "complete": not token,
            "partial_reason": "" if not token else "page_limit_reached",
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
    ) -> dict[str, Any]:
        target = self.object_get("dashboard", dashboard_id, branch=branch, revision_id=revision_id)
        relation_result = self.object_relations(dashboard_id)
        dependencies: list[dict[str, Any]] = []
        unresolved: list[dict[str, Any]] = []
        for relation in relation_result["relations"]:
            object_id = str(relation["id"])
            object_type = str(relation["type"])
            normalized_type = object_identity({"entryId": object_id, "scope": object_type})[1]
            if object_id == dashboard_id or normalized_type not in {
                "connection",
                "dataset",
                "wizard_chart",
                "editor_chart",
                "ql_chart",
                "dashboard",
            }:
                unresolved.append(relation)
                continue
            dependencies.append(self.object_get(normalized_type, object_id, branch=branch))
        result: dict[str, Any] = {
            "ok": True,
            "complete": not unresolved,
            "target": target,
            "relations": relation_result["relations"],
            "dependencies": dependencies,
            "unresolved_relations": unresolved,
        }
        if reference_dashboard_id:
            result["reference"] = self.object_get("dashboard", reference_dashboard_id, branch=branch)
        return result


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
