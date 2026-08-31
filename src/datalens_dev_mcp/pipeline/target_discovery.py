from __future__ import annotations

import re
from copy import deepcopy
from datetime import UTC, datetime
from typing import Any
from urllib.parse import parse_qs, urlparse

from datalens_dev_mcp.api.client import DataLensApiClient
from datalens_dev_mcp.api.errors import DataLensApiError
from datalens_dev_mcp.config import DataLensConfig
from datalens_dev_mcp.pipeline.dataset_preview import extract_dataset_fields
from datalens_dev_mcp.pipeline.object_locator import normalize_object_locator, provider_direct_url
from datalens_dev_mcp.pipeline.target_binding import create_live_target_binding
from datalens_dev_mcp.pipeline.target_graph import build_target_graph
from datalens_dev_mcp.pipeline.workflow_events import canonical_hash

URL_ID_RE = re.compile(r"^[A-Za-z0-9_]{8,64}")
CHART_ID_KEYS = frozenset({"chartId", "chart_id", "entryId", "entry_id", "targetEntryId", "target_entry_id"})
DATASET_ID_KEYS = frozenset({"datasetId", "dataset_id"})
CONNECTION_ID_KEYS = frozenset({"connectionId", "connection_id"})
FIELD_GUID_KEYS = frozenset({"guid", "fieldGuid", "field_guid"})
REVISION_KEYS = ("revId", "rev_id", "savedId", "saved_id", "revision", "revisionId")
EMBEDDED_ID_TOKEN_RE = re.compile(r"[A-Za-z0-9_]{8,64}")


class TargetDiscoveryError(RuntimeError):
    pass


class TargetDiscoveryService:
    def __init__(self, client: Any | None = None, *, max_objects: int = 50) -> None:
        self.client = client or DataLensApiClient(DataLensConfig.from_env())
        self.max_objects = max(1, min(200, int(max_objects)))

    def discover(
        self,
        contract: dict[str, Any],
        *,
        request_text: str = "",
        target_url: str = "",
    ) -> dict[str, Any]:
        # Request interpretation ends at TaskContract compilation. Discovery
        # consumes typed target fields (plus an explicit structured URL input)
        # and never recovers a target by reparsing the raw user turn.
        target = contract.get("target") or {}
        dashboard_id = str(target.get("dashboard_id") or parse_target_url(target_url) or "")
        workbook_id = str(target.get("workbook_id") or "")
        requested_ids = [str(item) for item in target.get("object_ids") or [] if str(item)]
        if str(contract.get("mode") or "") == "create" and workbook_id:
            return self._discover_create_workbook(
                workbook_id,
                technology=str(contract.get("route") or ""),
            )
        if not dashboard_id and workbook_id:
            selection = self._select_dashboard_from_workbook(workbook_id)
            if selection.get("status") != "success":
                return selection
            dashboard_id = str(selection["dashboard_id"])
        if not dashboard_id:
            return {
                "status": "blocked",
                "reason": "a dashboard URL or exact target ID is required before live discovery",
                "missing_facts": ["dashboard_id"],
                "question": "Какой точный URL или ID дашборда нужно использовать?",
            }
        try:
            return self._discover_dashboard(
                dashboard_id,
                workbook_id=workbook_id,
                requested_ids=requested_ids,
                verification=(
                    dict(contract.get("verification") or {})
                    if contract.get("operation_kind") == "verify_existing_effect"
                    else {}
                ),
                effect=dict(contract.get("effect") or {}),
            )
        except TargetDiscoveryError as exc:
            return {
                "status": "blocked",
                "reason": str(exc),
                "missing_facts": ["fresh_saved_target"],
                "question": None,
            }

    def _select_dashboard_from_workbook(self, workbook_id: str) -> dict[str, Any]:
        response = self.client.rpc_readonly("getWorkbookEntries", {"workbookId": workbook_id})
        entries = _entries(response)
        dashboards = [entry for entry in entries if _entry_type(entry) == "dashboard"]
        candidates = dashboards
        if len(candidates) == 1:
            return {
                "status": "success",
                "dashboard_id": str(candidates[0].get("entryId") or candidates[0].get("entry_id") or ""),
            }
        return {
            "status": "blocked",
            "reason": "workbook target is ambiguous after bounded inventory discovery",
            "missing_facts": ["dashboard_id"],
            "question": "Какой из найденных дашбордов является целевым?",
            "candidate_count": len(candidates),
            "candidates": [
                {
                    "object_id": str(item.get("entryId") or item.get("entry_id") or ""),
                    "title": str(item.get("displayKey") or item.get("name") or "")[:160],
                }
                for item in candidates[:10]
            ],
        }

    def _discover_create_workbook(self, workbook_id: str, *, technology: str) -> dict[str, Any]:
        calls: list[dict[str, Any]] = []
        inventory = self._read("getWorkbookEntries", {"workbookId": workbook_id}, calls)
        entries = _entries(inventory)
        total = int(inventory.get("total") or (inventory.get("result") or {}).get("total") or len(entries))
        limitations = []
        if total > len(entries):
            limitations.append("workbook inventory was bounded to the returned page")
        graph = build_target_graph(
            root_ids=[workbook_id],
            nodes=[
                _node(
                    "workbook",
                    workbook_id,
                    technology or "workbook",
                    "",
                    inventory,
                    workbook_id=workbook_id,
                )
            ],
            edges=[],
            provider_calls=calls,
            limitations=limitations,
        )
        inventory_hash = canonical_hash(inventory)
        binding = create_live_target_binding(
            workbook_id=workbook_id,
            dashboard_id="",
            object_ids=[workbook_id],
            object_types=["workbook"],
            saved_revision="",
            published_revision="",
            payload_hash=inventory_hash,
            layout_hash="",
            tabs_hash="",
            technology=technology or "workbook",
            target_graph_hash=str(graph["graph_hash"]),
        )
        return {
            "status": "success",
            "observed_at": _utc_now(),
            "target_binding": binding,
            "target_graph": graph,
            "baselines": {f"workbook-{workbook_id}-inventory": deepcopy(inventory)},
            "provider_calls": calls,
            "technology": technology or "workbook",
            "tab_count": 0,
            "dataset_count": sum(_entry_type(item) == "dataset" for item in entries),
            "connection_count": sum(_entry_type(item) == "connection" for item in entries),
            "field_count": 0,
            "inventory_count": len(entries),
        }

    def _discover_dashboard(
        self,
        dashboard_id: str,
        *,
        workbook_id: str,
        requested_ids: list[str],
        verification: dict[str, Any] | None = None,
        effect: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        calls: list[dict[str, Any]] = []
        baselines: dict[str, dict[str, Any]] = {}
        nodes: list[dict[str, Any]] = []
        edges: list[dict[str, str]] = []
        limitations: list[str] = []

        dashboard = self._read("getDashboard", {"dashboardId": dashboard_id, "branch": "saved"}, calls)
        dashboard_data = _object_data(dashboard, "dashboard")
        dashboard_entry = _entry(dashboard, "dashboard")
        if not dashboard_data and not dashboard_entry:
            raise TargetDiscoveryError("getDashboard returned no dashboard payload")
        workbook_id = workbook_id or str(_first_deep(dashboard, ("workbookId", "workbook_id")) or "")
        dashboard_revision = str(_first_deep(dashboard, REVISION_KEYS) or "")
        effect_kind = str((effect or {}).get("kind") or "")
        published_dashboard: dict[str, Any] = {}
        published_revision = ""
        if verification and effect_kind in {"published", "changed"}:
            published_dashboard = self._read(
                "getDashboard", {"dashboardId": dashboard_id, "branch": "published"}, calls
            )
            published_revision = str(_first_deep(published_dashboard, REVISION_KEYS) or "")
            if not _object_data(published_dashboard, "dashboard") and not _entry(published_dashboard, "dashboard"):
                raise TargetDiscoveryError("getDashboard published branch returned no dashboard payload")
            baselines[f"dashboard-{dashboard_id}-published"] = deepcopy(published_dashboard)
        tabs = dashboard_data.get("tabs") if isinstance(dashboard_data.get("tabs"), list) else []
        layout = dashboard_data.get("layout") or dashboard_data.get("blocks") or tabs
        baselines[f"dashboard-{dashboard_id}-saved"] = deepcopy(dashboard)
        dashboard_node = _node(
            "dashboard",
            dashboard_id,
            "dashboard",
            dashboard_revision,
            dashboard,
            workbook_id=workbook_id,
        )
        dashboard_node["published_revision"] = published_revision
        nodes.append(dashboard_node)

        inventory_types: dict[str, str] = {}
        if workbook_id:
            inventory = self._read("getWorkbookEntries", {"workbookId": workbook_id}, calls)
            entries = _entries(inventory)
            inventory_types = {
                str(item.get("entryId") or item.get("entry_id") or ""): _entry_type(item)
                for item in entries
                if item.get("entryId") or item.get("entry_id")
            }
            total = int(inventory.get("total") or (inventory.get("result") or {}).get("total") or len(entries))
            if total > len(entries):
                limitations.append("workbook inventory was bounded to the returned page")

        unsupported_requested = {
            item
            for item in requested_ids
            if item != dashboard_id and not _is_chart_type(inventory_types.get(item, "chart"))
        }
        if unsupported_requested:
            object_id = sorted(unsupported_requested)[0]
            raise TargetDiscoveryError(
                f"requested object {object_id} has unsupported target type "
                f"{inventory_types.get(object_id) or 'unknown'}"
            )
        requested_chart_ids = {
            item
            for item in requested_ids
            if item != dashboard_id and _is_chart_type(inventory_types.get(item, "chart"))
        }
        dashboard_chart_ids = {
            item
            for item in _collect_ids(dashboard_data, CHART_ID_KEYS)
            if item != dashboard_id and _is_chart_type(inventory_types.get(item, "chart"))
        }
        # An explicitly typed object target defines a request-scoped graph.
        # Hydrating every sibling widget both wastes calls and can evict the
        # requested object at the configured limit.
        chart_candidates = sorted(requested_chart_ids or dashboard_chart_ids)
        chart_limit = max(0, self.max_objects - len(nodes))
        chart_ids = chart_candidates[:chart_limit]
        if len(chart_candidates) > len(chart_ids):
            limitations.append("target graph reached the configured object limit")
        technologies: set[str] = set()
        dataset_ids: set[str] = set()
        for chart_id in chart_ids:
            object_type = inventory_types.get(chart_id, "chart")
            method, technology = _chart_read_route(object_type)
            if not method:
                if chart_id in requested_ids:
                    raise TargetDiscoveryError(
                        f"requested object {chart_id} has unsupported target type {object_type or 'unknown'}"
                    )
                limitations.append(f"no curated read route for chart type {object_type}")
                continue
            try:
                chart = self._read(method, {"chartId": chart_id, "branch": "saved"}, calls)
            except DataLensApiError as exc:
                if exc.http_status == 404 and chart_id not in requested_ids:
                    limitations.append("dashboard references an unavailable chart")
                    continue
                raise
            technologies.add(technology)
            revision = str(_first_deep(chart, REVISION_KEYS) or "")
            baselines[f"chart-{chart_id}-saved"] = deepcopy(chart)
            chart_node = _node(
                object_type,
                chart_id,
                technology,
                revision,
                chart,
                workbook_id=workbook_id,
            )
            chart_node["field_guids"] = sorted(_collect_ids(chart, FIELD_GUID_KEYS))
            nodes.append(chart_node)
            edges.append({"source": dashboard_id, "target": chart_id, "relation": "contains"})
            chart_dataset_ids = _collect_ids(chart, DATASET_ID_KEYS)
            chart_dataset_ids.update(_collect_inventory_references(chart, inventory_types, "dataset"))
            for dataset_id in chart_dataset_ids:
                dataset_ids.add(dataset_id)
                edges.append({"source": chart_id, "target": dataset_id, "relation": "uses_dataset"})

        connection_ids: set[str] = set()
        hydrated_dataset_ids: set[str] = set()
        for dataset_id in sorted(dataset_ids):
            if len(nodes) >= self.max_objects:
                limitations.append("target graph reached the configured object limit")
                break
            payload: dict[str, Any] = {"datasetId": dataset_id}
            if workbook_id:
                payload["workbookId"] = workbook_id
            dataset = self._read("getDataset", payload, calls)
            fields = extract_dataset_fields(dataset)
            field_catalog = [_field_projection(item) for item in fields]
            revision = str(_first_deep(dataset, REVISION_KEYS) or "")
            node = _node(
                "dataset",
                dataset_id,
                "dataset",
                revision,
                dataset,
                workbook_id=workbook_id,
            )
            node["field_catalog"] = field_catalog
            node["field_catalog_hash"] = canonical_hash(field_catalog)
            nodes.append(node)
            hydrated_dataset_ids.add(dataset_id)
            baselines[f"dataset-{dataset_id}-saved"] = deepcopy(dataset)
            for connection_id in _collect_ids(dataset, CONNECTION_ID_KEYS):
                connection_ids.add(connection_id)
                edges.append({"source": dataset_id, "target": connection_id, "relation": "uses_connection"})

        hydrated_connection_ids: set[str] = set()
        for connection_id in sorted(connection_ids):
            if len(nodes) >= self.max_objects:
                limitations.append("target graph reached the configured object limit")
                break
            payload = {"connectionId": connection_id}
            if workbook_id:
                payload["workbookId"] = workbook_id
            try:
                connection = self._read("getConnection", payload, calls)
            except DataLensApiError as exc:
                if exc.http_status in {403, 404} and connection_id not in requested_ids:
                    limitations.append("dashboard dependency connection is inaccessible")
                    continue
                raise
            nodes.append(
                _node(
                    "connection",
                    connection_id,
                    "connection",
                    "",
                    connection,
                    workbook_id=workbook_id,
                    include_payload_hash=False,
                )
            )
            hydrated_connection_ids.add(connection_id)

        graph = build_target_graph(
            root_ids=[dashboard_id],
            nodes=nodes,
            edges=edges,
            provider_calls=calls,
            limitations=limitations,
        )
        technology = next(iter(technologies)) if len(technologies) == 1 else "mixed" if technologies else "dashboard"
        binding = create_live_target_binding(
            workbook_id=workbook_id,
            dashboard_id=dashboard_id,
            object_ids=[str(item.get("object_id") or "") for item in nodes],
            object_types=[str(item.get("object_type") or "") for item in nodes],
            saved_revision=dashboard_revision,
            published_revision=published_revision,
            payload_hash=canonical_hash(dashboard),
            layout_hash=canonical_hash(layout),
            tabs_hash=canonical_hash(tabs),
            technology=technology,
            target_graph_hash=str(graph["graph_hash"]),
        )
        return {
            "status": "success",
            "observed_at": _utc_now(),
            "target_binding": binding,
            "target_graph": graph,
            "baselines": baselines,
            "provider_calls": calls,
            "technology": technology,
            "tab_count": len(tabs),
            "dataset_count": len(hydrated_dataset_ids),
            "connection_count": len(hydrated_connection_ids),
            "field_count": sum(len(item.get("field_catalog") or []) for item in nodes),
        }

    def _read(self, method: str, payload: dict[str, Any], calls: list[dict[str, Any]]) -> dict[str, Any]:
        try:
            response = self.client.rpc_readonly(method, payload)
        except DataLensApiError as exc:
            exc.provider_method = method
            raise
        calls.append(
            {
                "method": method,
                "request_hash": canonical_hash(payload),
                "response_hash": canonical_hash(response),
                "status": "success",
            }
        )
        return response


def parse_target_url(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    urls = [match.group(0).rstrip(".,;:])}") for match in re.finditer(r"https?://[^\s]+", text)]
    if not urls:
        return text if re.fullmatch(r"[A-Za-z0-9_]{8,64}", text) else ""
    datalens_urls = [url for url in urls if "datalens" in (urlparse(url).hostname or "").lower()]
    if not datalens_urls:
        return ""
    text = datalens_urls[0]
    parsed = urlparse(text)
    query = parse_qs(parsed.query)
    for key in ("dashboardId", "dashboard_id", "id"):
        value = str((query.get(key) or [""])[0])
        if re.fullmatch(r"[A-Za-z0-9_]{8,64}", value):
            return value
    segments = [segment for segment in parsed.path.split("/") if segment]
    for segment in reversed(segments):
        match = URL_ID_RE.match(segment)
        if match:
            return match.group(0)
    return ""


def _object_data(response: dict[str, Any], name: str) -> dict[str, Any]:
    result = response.get("result") if isinstance(response.get("result"), dict) else response
    object_value = result.get(name) if isinstance(result, dict) and isinstance(result.get(name), dict) else result
    data = object_value.get("data") if isinstance(object_value, dict) else None
    return data if isinstance(data, dict) else object_value if isinstance(object_value, dict) else {}


def _entry(response: dict[str, Any], name: str) -> dict[str, Any]:
    result = response.get("result") if isinstance(response.get("result"), dict) else response
    object_value = result.get(name) if isinstance(result, dict) and isinstance(result.get(name), dict) else result
    entry = object_value.get("entry") if isinstance(object_value, dict) else None
    return entry if isinstance(entry, dict) else {}


def _entries(response: dict[str, Any]) -> list[dict[str, Any]]:
    result = response.get("result") if isinstance(response.get("result"), dict) else response
    values = result.get("entries") if isinstance(result, dict) else None
    return [item for item in values or [] if isinstance(item, dict)]


def _entry_type(entry: dict[str, Any]) -> str:
    raw = (
        " ".join(str(entry.get(key) or "") for key in ("scope", "type", "entryType", "objectType", "kind"))
        .strip()
        .lower()
    )
    if "dashboard" in raw or raw == "dash":
        return "dashboard"
    if "dataset" in raw:
        return "dataset"
    if "connection" in raw or "connector" in raw:
        return "connection"
    if "wizard" in raw:
        return "wizard_chart"
    if "ql" in raw:
        return "ql_chart"
    if "editor" in raw or "advanced" in raw:
        return "editor_chart"
    value = str(entry.get("scope") or entry.get("type") or "").strip().lower()
    aliases = {"dash": "dashboard", "widget": "chart", "editor_advanced": "editor_chart"}
    return aliases.get(value, value)


def _is_chart_type(value: str) -> bool:
    return value in {
        "chart",
        "widget",
        "editor_chart",
        "editor_table",
        "wizard_chart",
        "ql_chart",
        "control",
        "markdown",
    }


def _chart_read_route(object_type: str) -> tuple[str, str]:
    normalized = str(object_type or "").lower()
    if normalized == "wizard_chart":
        return "getWizardChart", "wizard_native"
    if normalized == "ql_chart":
        return "getQLChart", "ql_explicit"
    if normalized in {"chart", "widget", "editor_chart", "editor_table", "control", "markdown"}:
        return "getEditorChart", "editor_advanced"
    return "", ""


def _collect_ids(value: Any, keys: frozenset[str]) -> set[str]:
    found: set[str] = set()
    if isinstance(value, dict):
        for key, item in value.items():
            if key in keys and isinstance(item, (str, int)) and str(item):
                found.add(str(item))
            found.update(_collect_ids(item, keys))
    elif isinstance(value, list):
        for item in value:
            found.update(_collect_ids(item, keys))
    return found


def _collect_inventory_references(
    value: Any,
    inventory_types: dict[str, str],
    object_type: str,
) -> set[str]:
    """Resolve embedded IDs only when workbook inventory proves their object type."""
    candidates = {object_id for object_id, kind in inventory_types.items() if kind == object_type}
    if not candidates:
        return set()
    found: set[str] = set()

    def visit(item: Any) -> None:
        if isinstance(item, dict):
            for nested in item.values():
                visit(nested)
        elif isinstance(item, list):
            for nested in item:
                visit(nested)
        elif isinstance(item, str):
            found.update(set(EMBEDDED_ID_TOKEN_RE.findall(item)) & candidates)

    visit(value)
    return found


def _first_deep(value: Any, keys: tuple[str, ...]) -> Any:
    if isinstance(value, dict):
        for key in keys:
            if key in value and value[key] is not None and value[key] != "":
                return value[key]
        for item in value.values():
            found = _first_deep(item, keys)
            if found is not None and found != "":
                return found
    elif isinstance(value, list):
        for item in value:
            found = _first_deep(item, keys)
            if found is not None and found != "":
                return found
    return None


def _node(
    object_type: str,
    object_id: str,
    technology: str,
    revision: str,
    response: dict[str, Any],
    *,
    workbook_id: str = "",
    include_payload_hash: bool = True,
) -> dict[str, Any]:
    direct = provider_direct_url(response)
    payload = {
        **normalize_object_locator(
            direct,
            object_type=object_type,
            object_id=object_id,
            workbook_id=workbook_id,
            url_source="provider_readback" if direct else "route_builder",
        ),
        "technology": technology,
        "saved_revision": revision,
    }
    if include_payload_hash:
        payload["payload_hash"] = canonical_hash(response)
    return payload


def _field_projection(value: dict[str, Any]) -> dict[str, Any]:
    return {
        "guid": str(value.get("guid") or ""),
        "name": str(value.get("name") or value.get("title") or ""),
        "type": str(value.get("type") or "unsupported"),
        "semantic_role": str(value.get("semantic_role") or ""),
        "aggregation": str(value.get("aggregation") or ""),
        "formula": str(value.get("formula") or ""),
        "source": str(value.get("source") or value.get("sourceColumn") or ""),
        "hidden": bool(value.get("hidden") or value.get("isHidden")),
        "unique": bool(value.get("unique") or value.get("isUnique")),
        "sensitive": bool(value.get("sensitive") or value.get("pii")),
    }


def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")
