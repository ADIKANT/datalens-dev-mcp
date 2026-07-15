from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class DashboardObjectFinding:
    rule: str
    severity: str
    path: str
    message: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class DashboardObjectGranularityResult:
    ok: bool
    publish_allowed: bool
    checked_object_count: int
    visual_object_count: int
    expected_visual_count: int
    table_count: int
    selector_count: int
    kpi_count: int
    findings: list[DashboardObjectFinding] = field(default_factory=list)
    schema_version: str = "2026-07-01.dashboard_object_granularity.v1"

    def to_dict(self) -> dict[str, Any]:
        return {**asdict(self), "findings": [finding.to_dict() for finding in self.findings]}


class DashboardObjectGraphContract:
    """Normalize dashboard object manifests into countable DataLens objects."""

    VISUAL_TYPES = {
        "advanced-chart_node",
        "advanced_editor_chart",
        "editor_advanced",
        "editor_chart",
        "chart_node",
        "wizard_map_native",
        "wizard_native",
        "wizard_chart",
        "ql_chart",
        "ymap_wizard_node",
        "indicator_node",
        "kpi_indicator",
        "kpi_node",
        "table_node",
    }
    TABLE_TYPES = {"table_node", "editor_table", "native_table"}
    SELECTOR_TYPES = {"control_node", "editor_js_control", "native_control", "selector"}
    KPI_TYPES = {"indicator_node", "kpi_indicator", "kpi_node"}
    ADVANCED_TYPES = {"advanced-chart_node", "advanced_editor_chart", "editor_advanced", "editor_chart"}

    def normalize(self, manifest: dict[str, Any]) -> dict[str, Any]:
        objects = _objects(manifest)
        visual_objects = [item for item in objects if self.object_type(item) in self.VISUAL_TYPES]
        return {
            "objects": objects,
            "visual_objects": visual_objects,
            "table_objects": [item for item in objects if self.object_type(item) in self.TABLE_TYPES],
            "selector_objects": [item for item in objects if self.object_type(item) in self.SELECTOR_TYPES],
            "kpi_objects": [item for item in objects if self.object_type(item) in self.KPI_TYPES or _looks_like_kpi(item)],
            "advanced_objects": [item for item in objects if self.object_type(item) in self.ADVANCED_TYPES],
            "expected_visual_count": _expected_visual_count(manifest),
            "item_object_ids": _manifest_item_object_ids(manifest),
        }

    def object_type(self, item: dict[str, Any]) -> str:
        return str(
            item.get("object_type")
            or item.get("entry_type")
            or item.get("type")
            or item.get("route")
            or item.get("selected_route")
            or ""
        ).strip().lower()


class DashboardObjectGranularityValidator:
    """Block one giant dashboard-like Advanced Editor object."""

    def __init__(self, contract: DashboardObjectGraphContract | None = None) -> None:
        self.contract = contract or DashboardObjectGraphContract()

    def validate(self, manifest: dict[str, Any]) -> DashboardObjectGranularityResult:
        normalized = self.contract.normalize(manifest)
        findings: list[DashboardObjectFinding] = []
        objects = normalized["objects"]
        expected_visual_count = normalized["expected_visual_count"]
        visual_objects = normalized["visual_objects"]
        static_reference = _is_static_reference_artifact(manifest)
        findings.extend(validate_semantic_role_object_mapping(manifest))
        if expected_visual_count and len(visual_objects) < expected_visual_count and not static_reference:
            findings.append(
                _finding(
                    "visual_object_count_below_manifest",
                    "$.objects",
                    (
                        f"dashboard expects {expected_visual_count} business visuals "
                        f"but only {len(visual_objects)} visual objects are declared"
                    ),
                )
            )
        if manifest.get("dashboard_like_advanced_editor") is True and not static_reference:
            findings.append(
                _finding(
                    "composite_dashboard_widget",
                    "$.dashboard_like_advanced_editor",
                    "dashboard-like Advanced Editor composite widgets are write-blocking",
                )
            )
        for index, item in enumerate(normalized["advanced_objects"]):
            path = f"$.objects[{index}]"
            findings.extend(_advanced_object_findings(item, path=path))
        for object_id in normalized["item_object_ids"]:
            if object_id and not any(_object_id(item) == object_id for item in objects):
                findings.append(
                    _finding(
                        "dashboard_item_missing_object_manifest",
                        "$.tabs",
                        f"dashboard item references object {object_id!r}, but it is absent from the object manifest",
                    )
                )
        errors = [finding for finding in findings if finding.severity == "error"]
        return DashboardObjectGranularityResult(
            ok=not errors,
            publish_allowed=not errors,
            checked_object_count=len(objects),
            visual_object_count=len(visual_objects),
            expected_visual_count=expected_visual_count,
            table_count=len(normalized["table_objects"]),
            selector_count=len(normalized["selector_objects"]),
            kpi_count=len(normalized["kpi_objects"]),
            findings=findings,
        )


def validate_dashboard_object_granularity(manifest: dict[str, Any]) -> DashboardObjectGranularityResult:
    return DashboardObjectGranularityValidator().validate(manifest)


def validate_semantic_role_object_mapping(manifest: dict[str, Any]) -> list[DashboardObjectFinding]:
    """Require distinct semantic roles to resolve to distinct live objects.

    Intentional reuse is explicit: every colliding binding must carry the same
    non-empty ``shared_object_key``. Widget ids are used as the semantic role
    when an explicit ``semantic_role`` is absent, which covers native dashboard
    payloads without forcing authoring-only metadata into DataLens requests.
    """

    bindings: dict[str, list[dict[str, str]]] = {}

    def walk(
        value: Any,
        *,
        path: str = "$",
        inherited_role: str = "",
        inherited_shared_key: str = "",
    ) -> None:
        if isinstance(value, dict):
            has_children = bool(
                any(isinstance(value.get(key), list) for key in ("tabs", "items", "blocks", "widgets"))
                or str(value.get("type") or "").strip().lower() in {"widget", "chart", "chart_widget"}
            )
            explicit_role = str(value.get("semantic_role") or "").strip()
            node_id = str(value.get("id") or value.get("widgetId") or value.get("widget_id") or "").strip()
            role = explicit_role or (node_id if has_children else inherited_role)
            shared_key = str(value.get("shared_object_key") or inherited_shared_key or "").strip()
            object_id = str(
                value.get("chartId")
                or value.get("chart_id")
                or value.get("objectId")
                or value.get("object_id")
                or ""
            ).strip()
            if object_id:
                binding_role = explicit_role or role or node_id
                if binding_role:
                    bindings.setdefault(object_id, []).append(
                        {"role": binding_role, "shared_object_key": shared_key, "path": path}
                    )
            for key, item in value.items():
                walk(
                    item,
                    path=f"{path}.{key}",
                    inherited_role=role,
                    inherited_shared_key=shared_key,
                )
        elif isinstance(value, list):
            for index, item in enumerate(value):
                walk(
                    item,
                    path=f"{path}[{index}]",
                    inherited_role=inherited_role,
                    inherited_shared_key=inherited_shared_key,
                )

    walk(manifest)
    findings: list[DashboardObjectFinding] = []
    for object_id, object_bindings in bindings.items():
        roles = {item["role"] for item in object_bindings if item["role"]}
        if len(roles) < 2:
            continue
        shared_keys = {item["shared_object_key"] for item in object_bindings}
        intentional_shared_binding = len(shared_keys) == 1 and bool(next(iter(shared_keys), ""))
        if intentional_shared_binding:
            continue
        findings.append(
            _finding(
                "semantic_role_object_mapping_not_injective",
                object_bindings[0]["path"],
                (
                    f"object {object_id!r} is bound to multiple semantic roles "
                    f"({', '.join(sorted(roles))}); use distinct object ids or the same explicit shared_object_key"
                ),
            )
        )
    return findings


def _objects(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    raw = manifest.get("objects") or manifest.get("object_manifest") or manifest.get("payloads") or []
    if isinstance(raw, list):
        return [item for item in raw if isinstance(item, dict)]
    return []


def _expected_visual_count(manifest: dict[str, Any]) -> int:
    raw = manifest.get("expected_visual_count") or manifest.get("business_visual_count")
    if isinstance(raw, int):
        return raw
    visuals = manifest.get("visuals")
    if isinstance(visuals, list):
        return len([item for item in visuals if isinstance(item, dict)])
    return 0


def _manifest_item_object_ids(manifest: dict[str, Any]) -> list[str]:
    ids: list[str] = []

    def walk(value: Any) -> None:
        if isinstance(value, dict):
            for key in ("object_id", "objectId", "chart_id", "chartId", "widget_id", "widgetId"):
                if value.get(key):
                    ids.append(str(value[key]))
            for item in value.values():
                walk(item)
        elif isinstance(value, list):
            for item in value:
                walk(item)

    walk(manifest.get("tabs") or manifest.get("dashboard") or {})
    return list(dict.fromkeys(ids))


def _advanced_object_findings(item: dict[str, Any], *, path: str) -> list[DashboardObjectFinding]:
    if _is_static_reference_artifact(item):
        return []
    findings: list[DashboardObjectFinding] = []
    declared_visuals = item.get("visual_count") or item.get("business_visual_count")
    if isinstance(declared_visuals, int) and declared_visuals > 1:
        findings.append(
            _finding(
                "advanced_editor_multiple_visuals",
                f"{path}.visual_count",
                "one Advanced Editor chart may render only one visual object",
            )
        )
    roles = item.get("visual_roles") or item.get("contains")
    if isinstance(roles, list) and len({str(role) for role in roles}) > 1:
        findings.append(
            _finding(
                "advanced_editor_multiple_dashboard_roles",
                f"{path}.visual_roles",
                "Advanced Editor object contains multiple dashboard roles",
            )
        )
    body = _joined_strings(item)
    lowered = body.lower()
    roles = _dashboard_roles_in_body(lowered)
    if len(roles) >= 2:
        findings.append(
            _finding(
                "composite_dashboard_widget",
                path,
                "Advanced Editor object combines dashboard roles; split filters, KPI, tables, and charts into native objects",
            )
        )
    if len(re.findall(r"<\s*h[12]\b", lowered)) > 1:
        findings.append(_finding("advanced_editor_multiple_sections", path, "multiple section headers inside one chart body"))
    if re.search(r"\b(period|sprint|team|selector|filter|фильтр)\b", lowered) and re.search(
        r"\b(control|select|dropdown|impacttabsids|selector-row)\b", lowered
    ):
        findings.append(
            _finding("selector_inside_advanced_editor_body", path, "selector/control UI is embedded inside a chart body")
        )
    if re.search(r"<\s*(table|thead|tbody|tr|td|th)\b", lowered) or "div-grid table" in lowered:
        findings.append(_finding("html_table_inside_advanced_editor_body", path, "tables must be table_node objects"))
    if _contains_kpi_card_grid(lowered):
        findings.append(_finding("kpi_card_grid_inside_advanced_editor_body", path, "KPI card grids are composite widgets"))
    if re.search(r"\b(methodology|методолог)", lowered) and re.search(r"<\s*h[12]\b|<\s*p\b", lowered):
        findings.append(
            _finding(
                "methodology_page_inside_advanced_editor_body",
                path,
                "methodology content should use markdown/text/table routes when available",
            )
        )
    title = str(item.get("native_title") or item.get("title") or "").strip().lower()
    if title and re.search(rf"<\s*h[12][^>]*>\s*{re.escape(title)}\b", lowered):
        findings.append(_finding("duplicate_inline_title", path, "chart body duplicates native dashboard title"))
    return findings


def _dashboard_roles_in_body(lowered: str) -> set[str]:
    roles: set[str] = set()
    if re.search(
        r"<\s*select\b|selector-row|data-selector|class\s*=\s*['\"][^'\"]*(?:selector|filter-control|control-panel)"
        r"|impacttabsids|dropdown|control_node|type\s*:\s*['\"]select['\"]",
        lowered,
    ):
        roles.add("selector")
    if _contains_kpi_card_grid(lowered):
        roles.add("kpi_grid")
    if re.search(r"<\s*(table|thead|tbody|tr|td|th)\b|role\s*=\s*['\"]table['\"]|div-grid\s+table|html_table", lowered):
        roles.add("table")
    if re.search(r"\b(chart-container|plot-area|chart-grid|line-chart|bar-chart|axis)\b|<\s*svg\b", lowered):
        roles.add("chart")
    return roles


def _contains_kpi_card_grid(lowered: str) -> bool:
    return bool(
        re.search(r"(kpi-card|metric-card|card-grid|cards-grid)", lowered)
        or ("grid-template-columns" in lowered and re.search(r"\b(kpi|metric|indicator)\b", lowered))
    )


def _is_static_reference_artifact(value: Any) -> bool:
    if isinstance(value, dict):
        for key in (
            "static_reference_artifact",
            "reference_only",
            "static_mock",
            "mock_reference",
            "allow_composite_advanced_editor_reference",
        ):
            if value.get(key) is True:
                return True
        intent = str(value.get("artifact_intent") or value.get("intent") or "").strip().lower()
        if intent in {"static_mock", "static_reference", "reference_only", "reference_artifact"}:
            return True
    return False


def _object_id(item: dict[str, Any]) -> str:
    return str(item.get("object_id") or item.get("id") or item.get("chart_id") or item.get("chartId") or "").strip()


def _looks_like_kpi(item: dict[str, Any]) -> bool:
    text = " ".join(str(item.get(key) or "") for key in ("id", "title", "role", "family")).lower()
    return "kpi" in text or "indicator" in text or "индикатор" in text


def _joined_strings(value: Any) -> str:
    parts: list[str] = []
    if isinstance(value, dict):
        for item in value.values():
            parts.append(_joined_strings(item))
    elif isinstance(value, list):
        for item in value:
            parts.append(_joined_strings(item))
    elif isinstance(value, str):
        parts.append(value)
    return "\n".join(parts)


def _finding(rule: str, path: str, message: str, *, severity: str = "error") -> DashboardObjectFinding:
    return DashboardObjectFinding(rule=rule, severity=severity, path=path, message=message)
