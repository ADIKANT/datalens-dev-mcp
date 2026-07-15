from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any, Literal
from urllib.parse import parse_qs, urlparse


TaskIntent = Literal[
    "implement",
    "fix",
    "enhance",
    "redesign",
    "update",
    "review",
    "plan",
    "unknown",
]
RouteIntent = Literal[
    "js",
    "advanced_editor",
    "wizard_native",
    "native_table",
    "native_pivot",
    "wizard_map_native",
    "ql_explicit",
    "unspecified",
]
PublishOverride = Literal["none", "plan_only", "dry_run", "draft", "save_only", "no_publish"]


@dataclass(frozen=True)
class NormalizedUserRequest:
    raw_text: str
    task_intent: TaskIntent
    route_intent: RouteIntent
    publish_override: PublishOverride = "none"
    destructive_actions: list[str] = field(default_factory=list)
    target_url: str = ""
    target_workbook_id: str = ""
    target_dashboard_id: str = ""
    target_chart_id: str = ""
    target_object_type: str = ""
    approval_sources: list[str] = field(default_factory=lambda: ["current_user_request"])
    evidence: list[str] = field(default_factory=list)

    @property
    def target_known(self) -> bool:
        return bool(self.target_dashboard_id or self.target_chart_id)

    @property
    def publish_allowed_by_text(self) -> bool:
        return self.publish_override == "none"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class UserRequestNormalizer:
    """Normalize free-form operator text into deterministic delivery signals."""

    IMPLEMENT_TERMS = {
        "implement": ("implement", "build", "create", "make", "apply", "publish", "save", "реализ", "сделай", "примени"),
        "fix": ("fix", "repair", "исправ", "почини"),
        "enhance": ("enhance", "improve", "extend", "доработ", "улучш"),
        "redesign": ("redesign", "переработ", "редизайн"),
        "update": ("update", "change", "modify", "обнов", "измени"),
    }
    REVIEW_TERMS = ("review", "audit", "inspect", "diagnose", "посмотри", "проверь", "оцени")
    PLAN_TERMS = ("plan", "план", "dry run", "dry_run", "без изменений", "только план")
    ROUTE_TERMS: dict[RouteIntent, tuple[str, ...]] = {
        "ql_explicit": ("ql chart", "ql-чарт", "через ql", "route=ql_explicit", "createqlchart", "updateqlchart"),
        "js": (" js", "javascript", "editor js", "на js", "через js"),
        "advanced_editor": ("advanced editor", "editor chart", "advanced-chart", "адвансед"),
        "wizard_native": ("wizard", "native datalens chart", "обычный график datalens", "через wizard", "визард"),
        "native_table": ("table", "таблиц", "таблич", "detail rows", "registry"),
        "native_pivot": ("pivot", "сводн", "cross-tab", "crosstab"),
        "wizard_map_native": ("map", "geo", "карта", "гео", "latitude", "longitude", "geopoint", "geopolygon"),
    }
    OVERRIDES: dict[PublishOverride, tuple[str, ...]] = {
        "plan_only": ("plan only", "только план", "без изменений"),
        "dry_run": ("dry run", "dry-run", "dry_run", "пробный"),
        "draft": ("draft", "черновик"),
        "save_only": ("save only", "only save", "только save", "только сохранить"),
        "no_publish": ("no publish", "do not publish", "don't publish", "не публикуй", "без publish"),
    }
    DESTRUCTIVE_TERMS = {
        "delete": ("delete", "remove object", "удали", "удалить"),
        "move": ("move", "перемести"),
        "permissions_change": ("permission", "access binding", "доступ", "права"),
        "credential_change": ("credential", "token", "password", "iam token", "секрет", "пароль"),
    }
    APPROVAL_SOURCES = {
        "goal_objective_file": ("goal objective", "goal-objective", "цель из файла"),
        "codex_tool_approval": ("codex tool approval", "tool approval", "approved tool", "разрешение codex"),
        "project_manifest_operator_approval": ("manifest approved", "operator approval"),
        "explicit_chat_approval": ("i approve", "я подтверждаю", "одобряю"),
    }
    URL_RE = re.compile(r"https?://[^\s)>\"]+", re.I)
    LABELED_ID_RE = re.compile(
        r"\b(?P<label>workbook|workbook_id|workbookId|dashboard|dashboard_id|dashboardId|chart|chart_id|chartId)"
        r"\s*[:=/]\s*(?P<id>[A-Za-z0-9_-]{5,64})",
        re.I,
    )

    def normalize(
        self,
        text: str,
        *,
        approval_sources: list[str] | None = None,
        context: dict[str, Any] | None = None,
    ) -> NormalizedUserRequest:
        raw = text or ""
        lowered = raw.lower()
        ctx = context or {}
        task_intent = self._task_intent(lowered)
        publish_override = self._publish_override(lowered)
        route_intent = self._route_intent(lowered)
        target_url = self._target_url(raw)
        extracted = self._extract_targets(raw, target_url=target_url)
        destructive = [
            action
            for action, terms in self.DESTRUCTIVE_TERMS.items()
            if any(term in lowered for term in terms)
        ]
        sources = ["current_user_request"]
        for source, terms in self.APPROVAL_SOURCES.items():
            if any(term in lowered for term in terms):
                sources.append(source)
        for source in approval_sources or []:
            if source and source not in sources:
                sources.append(source)
        return NormalizedUserRequest(
            raw_text=raw,
            task_intent=task_intent,
            route_intent=route_intent,
            publish_override=publish_override,
            destructive_actions=destructive,
            target_url=str(ctx.get("target_url") or target_url),
            target_workbook_id=str(ctx.get("target_workbook_id") or extracted.get("workbook_id") or ""),
            target_dashboard_id=str(ctx.get("target_dashboard_id") or extracted.get("dashboard_id") or ""),
            target_chart_id=str(ctx.get("target_chart_id") or extracted.get("chart_id") or ""),
            target_object_type=str(ctx.get("target_object_type") or extracted.get("object_type") or ""),
            approval_sources=sources,
            evidence=extracted.get("evidence", []),
        )

    def _task_intent(self, lowered: str) -> TaskIntent:
        for intent, terms in self.IMPLEMENT_TERMS.items():
            if any(term in lowered for term in terms):
                return intent  # type: ignore[return-value]
        if any(term in lowered for term in self.REVIEW_TERMS):
            return "review"
        if any(term in lowered for term in self.PLAN_TERMS):
            return "plan"
        return "unknown"

    def _publish_override(self, lowered: str) -> PublishOverride:
        for override, terms in self.OVERRIDES.items():
            if any(term in lowered for term in terms):
                return override
        return "none"

    def _route_intent(self, lowered: str) -> RouteIntent:
        if re.search(r"(?<![a-z0-9_])ql(?![a-z0-9_])", lowered) or any(
            term in lowered for term in self.ROUTE_TERMS["ql_explicit"]
        ):
            return "ql_explicit"
        map_terms = self.ROUTE_TERMS["wizard_map_native"]
        if re.search(r"(?<![a-z0-9_])(map|geo)(?![a-z0-9_])", lowered) or any(
            term in lowered for term in map_terms if term not in {"map", "geo"}
        ):
            return "wizard_map_native"
        for route in ("native_pivot", "native_table", "js", "advanced_editor", "wizard_native"):
            if any(term in lowered for term in self.ROUTE_TERMS[route]):  # type: ignore[index]
                return route  # type: ignore[return-value]
        return "unspecified"

    def _target_url(self, raw: str) -> str:
        match = self.URL_RE.search(raw)
        return match.group(0).rstrip(".,") if match else ""

    def _extract_targets(self, raw: str, *, target_url: str) -> dict[str, Any]:
        values: dict[str, Any] = {"evidence": []}
        if target_url:
            values.update(_ids_from_url(target_url))
            values["evidence"].append(f"user_url:{target_url}")
        for match in self.LABELED_ID_RE.finditer(raw):
            label = match.group("label").lower()
            value = match.group("id")
            if "workbook" in label:
                values["workbook_id"] = value
                values["evidence"].append(f"text_workbook_id:{value}")
            elif "dashboard" in label:
                values["dashboard_id"] = value
                values["object_type"] = "dashboard"
                values["evidence"].append(f"text_dashboard_id:{value}")
            elif "chart" in label:
                values["chart_id"] = value
                values["object_type"] = "chart"
                values["evidence"].append(f"text_chart_id:{value}")
        return values


def normalize_user_request(
    text: str,
    *,
    approval_sources: list[str] | None = None,
    context: dict[str, Any] | None = None,
) -> NormalizedUserRequest:
    return UserRequestNormalizer().normalize(text, approval_sources=approval_sources, context=context)


def _ids_from_url(url: str) -> dict[str, str]:
    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    result: dict[str, str] = {}
    for key, target_key in (
        ("workbookId", "workbook_id"),
        ("workbook_id", "workbook_id"),
        ("dashboardId", "dashboard_id"),
        ("dashboard_id", "dashboard_id"),
        ("chartId", "chart_id"),
        ("chart_id", "chart_id"),
        ("id", "dashboard_id"),
    ):
        if query.get(key):
            result[target_key] = query[key][0]
    parts = [part for part in parsed.path.split("/") if part]
    if "datalens" in (parsed.hostname or "").lower() and parts:
        seo_dashboard = re.match(r"^(?P<id>[A-Za-z0-9]{13})(?:-|$)", parts[0])
        if seo_dashboard:
            result.setdefault("dashboard_id", seo_dashboard.group("id"))
            result.setdefault("object_type", "dashboard")
    for index, part in enumerate(parts):
        lowered = part.lower()
        next_part = parts[index + 1] if index + 1 < len(parts) else ""
        if lowered in {"workbook", "workbooks"} and next_part:
            result.setdefault("workbook_id", next_part)
        elif lowered in {"dashboard", "dashboards"} and next_part:
            result.setdefault("dashboard_id", next_part)
            result.setdefault("object_type", "dashboard")
        elif lowered in {"chart", "charts"} and next_part:
            result.setdefault("chart_id", next_part)
            result.setdefault("object_type", "chart")
    return result
