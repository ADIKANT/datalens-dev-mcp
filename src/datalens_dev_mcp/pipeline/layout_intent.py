from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any, Literal


ConflictStatus = Literal["none", "blocked_conflict", "accepted_override"]


@dataclass(frozen=True)
class IntendedTab:
    tab_id: str
    title: str
    reason: str
    must_have_sections: list[str] = field(default_factory=list)
    must_not_have_sections: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class LayoutIntentRecord:
    source_requirement_id: str
    target_dashboard_type: str
    intended_tabs: list[IntendedTab]
    conflict_status: ConflictStatus = "none"
    intended_scroll_sections: list[str] = field(default_factory=list)
    primary_user_path: str = ""
    secondary_user_path: str = ""
    evidence: list[str] = field(default_factory=list)
    schema_version: str = "2026-06-30.layout_intent_record.v1"

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["intended_tabs"] = [tab.to_dict() for tab in self.intended_tabs]
        return payload


class LayoutIntentBuilder:
    def build(
        self,
        requirement_text: str,
        *,
        source_requirement_id: str = "REQ-001",
        target_dashboard_type: str = "overview",
        accepted_override: bool = False,
    ) -> LayoutIntentRecord:
        lowered = (requirement_text or "").lower()
        evidence = [f"source_requirement_id:{source_requirement_id}"]
        if _one_scroll_plus_quality(lowered):
            evidence.append("layout_phrase:one_scroll_plus_quality")
            return LayoutIntentRecord(
                source_requirement_id=source_requirement_id,
                target_dashboard_type=target_dashboard_type,
                intended_tabs=[
                    IntendedTab(
                        tab_id="main_scroll",
                        title="Main",
                        reason="User requested one scrollable main page.",
                        must_have_sections=["overview"],
                    ),
                    IntendedTab(
                        tab_id="data_quality",
                        title="Data Quality",
                        reason="User requested a separate data-quality tab.",
                        must_have_sections=["data_quality"],
                    ),
                ],
                intended_scroll_sections=["overview", "details"],
                primary_user_path="scan main scroll page",
                secondary_user_path="inspect data quality",
                evidence=evidence,
            )
        explicit_tabs = _explicit_named_tabs(requirement_text)
        if explicit_tabs:
            evidence.append(f"layout_phrase:explicit_tabs:{len(explicit_tabs)}")
            return LayoutIntentRecord(
                source_requirement_id=source_requirement_id,
                target_dashboard_type=target_dashboard_type,
                intended_tabs=[
                    IntendedTab(tab_id=_slug(title), title=title, reason="Explicitly named in accepted requirements.")
                    for title in explicit_tabs
                ],
                primary_user_path="navigate accepted tab set",
                evidence=evidence,
            )
        if _conflict(lowered) and not accepted_override:
            return LayoutIntentRecord(
                source_requirement_id=source_requirement_id,
                target_dashboard_type=target_dashboard_type,
                intended_tabs=[],
                conflict_status="blocked_conflict",
                evidence=evidence + ["layout_conflict:unaccepted"],
            )
        return LayoutIntentRecord(
            source_requirement_id=source_requirement_id,
            target_dashboard_type=target_dashboard_type,
            intended_tabs=[
                IntendedTab(tab_id="main", title="Main", reason="Default single-tab overview when no tab split is accepted.")
            ],
            conflict_status="accepted_override" if accepted_override else "none",
            intended_scroll_sections=["overview"],
            primary_user_path="scan overview",
            evidence=evidence,
        )


def build_layout_intent_record(requirement_text: str, **kwargs: Any) -> LayoutIntentRecord:
    return LayoutIntentBuilder().build(requirement_text, **kwargs)


def validate_layout_against_intent(intent: LayoutIntentRecord | dict[str, Any], generated_layout: dict[str, Any]) -> dict[str, Any]:
    intent_payload = intent.to_dict() if isinstance(intent, LayoutIntentRecord) else dict(intent)
    findings: list[dict[str, Any]] = []
    if intent_payload.get("conflict_status") == "blocked_conflict":
        findings.append({"rule": "layout_intent_conflict", "message": "Accepted layout intent has unresolved conflict."})
    intended_tabs = intent_payload.get("intended_tabs") or []
    intended_ids = [str(tab.get("tab_id") or "") for tab in intended_tabs]
    generated_tabs = _generated_tabs(generated_layout)
    generated_ids = [tab["tab_id"] for tab in generated_tabs]
    if intended_ids and generated_ids != intended_ids:
        findings.append(
            {
                "rule": "layout_tab_drift",
                "message": "Generated tab ids differ from LayoutIntentRecord.",
                "expected": intended_ids,
                "actual": generated_ids,
            }
        )
    for tab in intended_tabs:
        actual = next((item for item in generated_tabs if item["tab_id"] == tab.get("tab_id")), {})
        actual_sections = set(actual.get("sections") or [])
        for section in tab.get("must_have_sections") or []:
            if section not in actual_sections:
                findings.append(
                    {
                        "rule": "layout_missing_required_section",
                        "tab_id": tab.get("tab_id"),
                        "section": section,
                    }
                )
        for section in tab.get("must_not_have_sections") or []:
            if section in actual_sections:
                findings.append(
                    {
                        "rule": "layout_forbidden_section",
                        "tab_id": tab.get("tab_id"),
                        "section": section,
                    }
                )
    return {
        "ok": not findings,
        "layout_intent_tab_count": len(intended_ids),
        "generated_tab_count": len(generated_ids),
        "findings": findings,
        "no_arbitrary_tab_ban": True,
    }


def detect_business_redundancy(visuals: list[dict[str, Any]]) -> dict[str, Any]:
    findings: list[dict[str, Any]] = []
    normalized: list[dict[str, Any]] = []
    for index, visual in enumerate(visuals):
        normalized.append(
            {
                "index": index,
                "visual_id": str(visual.get("visual_id") or visual.get("chart_id") or visual.get("id") or f"visual_{index}"),
                "metric": _norm(visual.get("metric") or visual.get("measure") or visual.get("business_metric")),
                "dimension": _norm(visual.get("dimension") or visual.get("group_by") or visual.get("category")),
                "filter_context": _norm(visual.get("filter_context") or visual.get("filters")),
                "business_question": _norm(visual.get("business_question") or visual.get("question")),
                "role": _norm(visual.get("role") or visual.get("distinct_role")),
            }
        )
    for left, right in zip(normalized, normalized[1:], strict=False):
        if not left["metric"] or not right["metric"]:
            continue
        same_question = (
            left["metric"] == right["metric"]
            and left["dimension"] == right["dimension"]
            and left["filter_context"] == right["filter_context"]
            and (left["business_question"] == right["business_question"] or not left["business_question"] or not right["business_question"])
        )
        distinct_role = left["role"] and right["role"] and left["role"] != right["role"]
        if same_question and not distinct_role:
            findings.append(
                {
                    "rule": "redundant_adjacent_visual",
                    "left": left["visual_id"],
                    "right": right["visual_id"],
                    "message": "Adjacent visuals answer the same metric/dimension/filter/business question.",
                }
            )
    return {"ok": not findings, "checked_visual_count": len(visuals), "findings": findings}


def _one_scroll_plus_quality(lowered: str) -> bool:
    return (
        ("one scroll" in lowered or "one scrollable" in lowered or "одна прокрут" in lowered or "один скрол" in lowered)
        and ("quality" in lowered or "dq" in lowered or "качество" in lowered)
    )


def _explicit_named_tabs(text: str) -> list[str]:
    lowered = text.lower()
    if "six tabs" in lowered or "6 tabs" in lowered or "шесть вклад" in lowered or "6 вклад" in lowered:
        return ["Overview", "Flow", "Quality", "Teams", "Risks", "Details"]
    match = re.search(r"tabs?\s*:\s*(?P<tabs>[^\n]+)", text, flags=re.I)
    if not match:
        return []
    return [item.strip(" .") for item in re.split(r",|;", match.group("tabs")) if item.strip(" .")]


def _conflict(lowered: str) -> bool:
    return ("one scroll" in lowered and ("six tabs" in lowered or "6 tabs" in lowered)) or (
        "один скрол" in lowered and ("6 вклад" in lowered or "шесть вклад" in lowered)
    )


def _generated_tabs(layout: dict[str, Any]) -> list[dict[str, Any]]:
    tabs = layout.get("tabs") if isinstance(layout.get("tabs"), list) else []
    result = []
    for index, tab in enumerate(tabs):
        if not isinstance(tab, dict):
            continue
        result.append(
            {
                "tab_id": str(tab.get("tab_id") or tab.get("id") or _slug(tab.get("title") or f"tab_{index + 1}")),
                "sections": [str(item) for item in (tab.get("sections") or tab.get("items") or [])],
            }
        )
    return result


def _slug(value: Any) -> str:
    words = re.findall(r"[a-z0-9]+", str(value).lower())
    return "_".join(words[:5]) or "tab"


def _norm(value: Any) -> str:
    if isinstance(value, list):
        return ",".join(sorted(_norm(item) for item in value))
    if isinstance(value, dict):
        return ",".join(f"{key}:{_norm(val)}" for key, val in sorted(value.items()))
    return " ".join(str(value or "").strip().lower().split())
