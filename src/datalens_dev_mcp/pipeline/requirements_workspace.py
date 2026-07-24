from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from datalens_dev_mcp.pipeline.chart_param_matrix import get_chart_param_spec
from datalens_dev_mcp.pipeline.artifacts import read_text, write_text
from datalens_dev_mcp.pipeline.decision_patches import (
    apply_decision_contract_to_chart_plan,
    decision_contract_drift_issues,
    load_user_decision_ledger,
    normalize_decision_patch,
    record_user_decision_patch,
)
from datalens_dev_mcp.pipeline.negative_requirements import (
    load_negative_requirement_ledger,
    record_negative_requirements,
    sanitize_user_decision_line,
)
from datalens_dev_mcp.pipeline.visual_decisions import decide_chart, validate_chart_decision_record
from datalens_dev_mcp.runtime_resources import resource_json


DASHBOARD_TYPE_MODEL_RESOURCE = "config/datalens_dashboard_type_model.json"

REQUIREMENTS_FILES = (
    "source_inputs.md",
    "s2t.md",
    "data_architecture.md",
    "datasets.md",
    "connectors.md",
    "fields.md",
    "metrics.md",
    "dashboard_requirements.md",
    "dashboard_map.md",
    "dashboard_canvas.md",
    "dashboard_pages.md",
    "charts.md",
    "selectors.md",
    "object_relations.md",
    "user_decisions.md",
    "implementation_plan.md",
    "change_log.md",
)


DEFAULT_HEADERS = {
    "source_inputs.md": "# Source Inputs\n\n",
    "s2t.md": "# S2T\n\n",
    "data_architecture.md": "# Data Architecture\n\n",
    "datasets.md": "# Datasets\n\n",
    "connectors.md": "# Connectors\n\n",
    "fields.md": "# Fields\n\n",
    "metrics.md": "# Metrics\n\n",
    "dashboard_requirements.md": "# Dashboard Requirements\n\n",
    "dashboard_map.md": (
        "# Dashboard Map\n\n"
        "## Roles\n\n"
        "## Objects And Processes\n\n"
        "## Dashboards And Priorities\n\n"
        "## Metrics And Cuts\n\n"
        "## Architecture\n\n"
        "## Operational Lifecycle\n\n"
    ),
    "dashboard_canvas.md": (
        "# Dashboard Canvas\n\n"
        "## Purpose And Audience\n\n"
        "## Scenarios And Decisions\n\n"
        "## Data Architecture\n\n"
        "## Visual Blocks\n\n"
        "## Interactions And Success Criteria\n\n"
        "## Conditional UX Acceptance\n\n"
    ),
    "dashboard_pages.md": "# Dashboard Pages\n\n",
    "charts.md": "# Charts\n\n",
    "selectors.md": "# Selectors\n\n",
    "object_relations.md": "# Object Relations\n\n",
    "user_decisions.md": "# User Decisions\n\n",
    "implementation_plan.md": "# Implementation Plan\n\nSource of truth: `requirements/*.md`.\n",
    "change_log.md": "# Change Log\n\n| Time | Change |\n| --- | --- |\n",
}


ROLE_TO_FILE = {
    "source": "source_inputs.md",
    "s2t": "s2t.md",
    "data_architecture": "data_architecture.md",
    "dataset": "datasets.md",
    "connector": "connectors.md",
    "field": "fields.md",
    "metric": "metrics.md",
    "dashboard": "dashboard_requirements.md",
    "dashboard_map": "dashboard_map.md",
    "dashboard_canvas": "dashboard_canvas.md",
    "page": "dashboard_pages.md",
    "chart": "charts.md",
    "selector": "selectors.md",
    "relation": "object_relations.md",
}


REQUIREMENT_KEYWORDS: dict[str, tuple[str, ...]] = {
    "data_architecture.md": (
        "architecture",
        "lineage",
        "join",
        "grain",
        "relationship",
        "архитектур",
        "линей",
        "связь",
        "связк",
        "грануляр",
        "уровень агрегац",
    ),
    "datasets.md": (
        "dataset",
        "table",
        "source",
        "витрин",
        "датасет",
        "таблиц",
        "источник",
    ),
    "connectors.md": ("connector", "connection", "коннектор", "подключен"),
    "fields.md": ("field", "column", "attribute", "поле", "колонк", "атрибут"),
    "metrics.md": (
        "metric",
        "kpi",
        "measure",
        "formula",
        "aggregation",
        "метрик",
        "показател",
        "формул",
        "расчет",
        "расчёт",
        "агрегац",
    ),
    "dashboard_pages.md": ("page", "tab", "section", "страниц", "вкладк", "секци", "раздел"),
    "charts.md": (
        "chart",
        "visual",
        "graph",
        "use case",
        "чарт",
        "визуализац",
        "график",
        "диаграм",
    ),
    "selectors.md": (
        "selector",
        "filter",
        "control",
        "селектор",
        "фильтр",
        "контрол",
    ),
    "object_relations.md": (
        "relation",
        "target",
        "affects",
        "depends",
        "join",
        "controls",
        "связь",
        "влияет",
        "зависит",
        "управляет",
    ),
    "dashboard_map.md": (
        "role",
        "process",
        "priority",
        "owner",
        "architecture",
        "роль",
        "процесс",
        "приоритет",
        "владелец",
        "архитектур",
    ),
    "dashboard_canvas.md": (
        "audience",
        "scenario",
        "decision",
        "action",
        "success",
        "freshness",
        "quality",
        "аудитор",
        "сценари",
        "решен",
        "действ",
        "успех",
        "свежест",
        "качеств",
        "назначен",
    ),
}


TABLE_HEADER_HINTS: dict[str, tuple[str, ...]] = {
    "datasets.md": ("source", "dataset", "table", "источник", "витрина", "таблица"),
    "fields.md": ("field", "column", "attribute", "поле", "поля", "колонка", "атрибут"),
    "metrics.md": ("metric", "kpi", "measure", "formula", "метрик", "показатель", "формула"),
    "dashboard_pages.md": ("tab", "order", "page", "section", "вкладка", "порядок", "раздел"),
    "charts.md": ("chart", "use case", "visualization", "чарт", "визуализация"),
    "selectors.md": ("selector", "filter", "control", "селектор", "фильтр", "контрол"),
    "dashboard_canvas.md": ("description", "decision", "action", "описание", "решение", "действие"),
}


def initialize_requirements_workspace(project_root: str | Path) -> dict[str, Any]:
    root = Path(project_root)
    req = root / "requirements"
    created = []
    for file_name in REQUIREMENTS_FILES:
        path = req / file_name
        if not path.exists():
            write_text(path, DEFAULT_HEADERS[file_name])
            created.append(str(path.relative_to(root)))
    update_implementation_plan(project_root)
    return {
        "requirements_root": str(req),
        "files": [str((req / name).relative_to(root)) for name in REQUIREMENTS_FILES],
        "created": created,
    }


def ingest_requirements_markdown(
    project_root: str | Path,
    *,
    markdown_text: str,
    source_name: str = "user_input",
    role: str = "dashboard",
) -> dict[str, Any]:
    if not markdown_text.strip():
        return {"ok": False, "error": {"category": "missing_input", "message": "markdown_text is required"}}
    initialize_requirements_workspace(project_root)
    root = Path(project_root)
    target_name = ROLE_TO_FILE.get(role, "dashboard_requirements.md")
    target = root / "requirements" / target_name
    block = f"\n## {source_name}\n\n{markdown_text.strip()}\n"
    write_text(target, read_text(target) + block)
    write_text(root / "requirements" / "source_inputs.md", read_text(root / "requirements" / "source_inputs.md") + block)
    extracted = _extract_requirement_lines(markdown_text)
    table_diagnostics = _requirement_table_diagnostics(markdown_text)
    negative_requirements = record_negative_requirements(root, markdown_text, decision_id=source_name)
    for file_name, lines in extracted.items():
        if lines:
            existing = read_text(root / "requirements" / file_name)
            write_text(root / "requirements" / file_name, existing + f"\n## Extracted from {source_name}\n\n" + "\n".join(lines) + "\n")
    blueprint = _write_map_canvas_blueprint(root, source_text=markdown_text, source_name=source_name)
    _append_chart_catalog(root, source_text=markdown_text, source_name=source_name, selection=blueprint)
    _append_object_relation_placeholders(root, source_text=markdown_text, source_name=source_name, selection=blueprint)
    _append_change(root, f"Ingested `{source_name}` as `{role}`.")
    update_implementation_plan(project_root)
    return {
        "ok": True,
        "target": f"requirements/{target_name}",
        "extracted": {key: len(value) for key, value in extracted.items()},
        "dashboard_blueprint": blueprint,
        "negative_requirements": negative_requirements,
        "requirement_table_diagnostics": table_diagnostics,
        # Diagnose only authored source inputs. Generated chart-catalog rows
        # intentionally contain planning placeholders and must not become
        # false missing-BRD-cell questions on the same ingest.
        "critical_questions": _critical_requirement_questions(read_text(root / "requirements" / "source_inputs.md")),
    }


def load_dashboard_type_model() -> dict[str, Any]:
    return resource_json(DASHBOARD_TYPE_MODEL_RESOURCE)


def select_dashboard_blueprint(
    request_text: str,
    *,
    data_profile: dict[str, Any] | None = None,
) -> dict[str, Any]:
    model = load_dashboard_type_model()
    text = (request_text or "").lower()
    data_profile = data_profile or {}
    scored: list[dict[str, Any]] = []
    for dashboard_type, spec in model["dashboard_types"].items():
        keywords = spec.get("selection_keywords") or []
        matched = [keyword for keyword in keywords if keyword.lower() in text]
        score = len(matched) * 3
        if dashboard_type == "self_service" and len(data_profile.get("fields") or []) >= 8:
            score += 2
            matched.append("many_fields")
        if dashboard_type == "overview" and any(word in text for word in ("dashboard", "monitor", "state")):
            score += 1
        scored.append({"dashboard_type": dashboard_type, "score": score, "matched_keywords": matched, "blueprint": spec})
    scored.sort(key=lambda item: (-item["score"], item["dashboard_type"]))
    selected = scored[0] if scored and scored[0]["score"] > 0 else {
        "dashboard_type": "overview",
        "score": 0,
        "matched_keywords": [],
        "blueprint": model["dashboard_types"]["overview"],
    }
    blueprint = selected["blueprint"]
    confidence = "high" if selected["score"] >= 6 else "medium" if selected["score"] >= 3 else "low"
    operational_lifecycle = _operational_lifecycle_contract(
        model,
        text=text,
        dashboard_type=selected["dashboard_type"],
    )
    conditional_ux = _conditional_ux_acceptance(model, text=text, data_profile=data_profile)
    acceptance_checklist = list(blueprint["acceptance_checklist"])
    required_inputs_questions = list(blueprint["required_inputs_questions"])
    if operational_lifecycle["required"]:
        acceptance_checklist.extend(operational_lifecycle["acceptance_checklist"])
        required_inputs_questions.extend(operational_lifecycle["required_questions"])
    acceptance_checklist.extend(conditional_ux["acceptance_checklist"])
    return {
        "schema_version": "2026-07-13.dashboard_blueprint_selection.v2",
        "dashboard_type": selected["dashboard_type"],
        "confidence": confidence,
        "matched_keywords": selected["matched_keywords"],
        "reason": blueprint["selection_reason"],
        "job_to_be_done": blueprint["job_to_be_done"],
        "recommended_layout": blueprint["recommended_layout"],
        "recommended_chart_families": blueprint["recommended_chart_families"],
        "selector_filter_behavior": blueprint["selector_filter_behavior"],
        "navigation_relations": blueprint["navigation_relations"],
        "expected_interactivity": blueprint["expected_interactivity"],
        "acceptance_checklist": list(dict.fromkeys(acceptance_checklist)),
        "required_inputs_questions": list(dict.fromkeys(required_inputs_questions)),
        "operational_lifecycle": operational_lifecycle,
        "conditional_ux_acceptance": conditional_ux,
    }


def _operational_lifecycle_contract(
    model: dict[str, Any],
    *,
    text: str,
    dashboard_type: str,
) -> dict[str, Any]:
    policy = model.get("operational_lifecycle_contract") or {}
    matched_keywords = [
        keyword for keyword in policy.get("trigger_keywords") or [] if str(keyword).lower() in text.lower()
    ]
    type_triggered = dashboard_type in set(policy.get("trigger_dashboard_types") or [])
    required = bool(type_triggered or matched_keywords)
    return {
        "required": required,
        "triggered_by_dashboard_type": type_triggered,
        "matched_keywords": matched_keywords,
        "fields": list(policy.get("fields") or []) if required else [],
        "required_questions": list(policy.get("required_questions") or []) if required else [],
        "acceptance_checklist": list(policy.get("acceptance_checklist") or []) if required else [],
    }


def _conditional_ux_acceptance(
    model: dict[str, Any],
    *,
    text: str,
    data_profile: dict[str, Any],
) -> dict[str, Any]:
    lowered = text.lower()
    conditions: list[dict[str, Any]] = []
    acceptance: list[str] = []
    for rule in model.get("conditional_ux_acceptance") or []:
        matched = [keyword for keyword in rule.get("keywords") or [] if str(keyword).lower() in lowered]
        if rule.get("condition_id") == "dense_table_or_export" and len(data_profile.get("fields") or []) >= 8:
            matched.append("many_fields_profile")
        if not matched:
            continue
        checklist = list(rule.get("acceptance_checklist") or [])
        conditions.append(
            {
                "condition_id": rule.get("condition_id") or "",
                "matched_keywords": matched,
                "acceptance_checklist": checklist,
            }
        )
        acceptance.extend(checklist)
    return {
        "required": bool(conditions),
        "conditions": conditions,
        "acceptance_checklist": list(dict.fromkeys(acceptance)),
    }


def populate_dashboard_map_canvas(
    project_root: str | Path,
    *,
    source_text: str,
    source_name: str = "user_input",
    data_profile: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if not source_text.strip():
        return {"ok": False, "error": {"category": "missing_input", "message": "source_text is required"}}
    initialize_requirements_workspace(project_root)
    root = Path(project_root)
    selection = _write_map_canvas_blueprint(root, source_text=source_text, source_name=source_name, data_profile=data_profile)
    _append_chart_catalog(root, source_text=source_text, source_name=source_name, selection=selection)
    _append_object_relation_placeholders(root, source_text=source_text, source_name=source_name, selection=selection)
    _append_change(root, f"Populated Dashboard Map/Canvas from `{source_name}` using `{selection['dashboard_type']}` blueprint.")
    update_implementation_plan(project_root)
    return {"ok": True, "dashboard_blueprint": selection, "paths": ["requirements/dashboard_map.md", "requirements/dashboard_canvas.md"]}


def update_user_decision(
    project_root: str | Path,
    *,
    decision_text: str,
    decision_id: str = "",
    decision_patch: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if not decision_text.strip():
        return {"ok": False, "error": {"category": "missing_input", "message": "decision_text is required"}}
    initialize_requirements_workspace(project_root)
    root = Path(project_root)
    identifier = decision_id or f"DEC-{_timestamp().replace(':', '').replace('-', '')}"
    normalized_patch: dict[str, Any] | None = None
    if decision_patch is not None:
        normalized_patch, patch_issues = normalize_decision_patch(
            decision_patch,
            ledger=load_user_decision_ledger(root),
        )
        if patch_issues:
            return {
                "ok": False,
                "error": {
                    "category": "invalid_decision_patch",
                    "message": "; ".join(patch_issues),
                },
                "issues": patch_issues,
            }
    negative_requirements = record_negative_requirements(root, decision_text, decision_id=identifier)
    stored_decision_text = sanitize_user_decision_line(decision_text, negative_requirements)
    line = f"- `{identifier}`: {stored_decision_text}\n"
    path = root / "requirements" / "user_decisions.md"
    write_text(path, read_text(path) + "\n" + line)
    patch_result: dict[str, Any] | None = None
    if normalized_patch is not None:
        patch_result = record_user_decision_patch(
            root,
            decision_id=identifier,
            decision_text=stored_decision_text,
            decision_patch=normalized_patch,
        )
        if not patch_result["ok"]:
            return patch_result
    _append_change(root, f"Recorded user decision `{identifier}`.")
    update_implementation_plan(project_root)
    return {
        "ok": True,
        "decision_id": identifier,
        "path": "requirements/user_decisions.md",
        "negative_requirements": negative_requirements,
        **({"decision_patch": patch_result} if patch_result is not None else {}),
    }


def update_implementation_plan(project_root: str | Path) -> dict[str, Any]:
    root = Path(project_root)
    req = root / "requirements"
    req.mkdir(parents=True, exist_ok=True)
    for file_name in REQUIREMENTS_FILES:
        path = req / file_name
        if not path.exists():
            write_text(path, DEFAULT_HEADERS[file_name])
    known = {
        "dashboard_requirements": _last_nonempty_lines(read_text(req / "dashboard_requirements.md"), 6),
        "metrics": _last_nonempty_lines(read_text(req / "metrics.md"), 8),
        "fields": _last_nonempty_lines(read_text(req / "fields.md"), 8),
        "dashboard_map": _last_nonempty_lines(read_text(req / "dashboard_map.md"), 8),
        "dashboard_canvas": _last_nonempty_lines(read_text(req / "dashboard_canvas.md"), 8),
        "charts": _last_nonempty_lines(read_text(req / "charts.md"), 8),
        "selectors": _last_nonempty_lines(read_text(req / "selectors.md"), 8),
        "decisions": _last_nonempty_lines(read_text(req / "user_decisions.md"), 8),
    }
    combined_text = read_persisted_source_requirement_text(project_root)
    blueprint_plan = build_dashboard_blueprint_plan(project_root, update_plan=False, source_text=combined_text)
    content = [
        "# Implementation Plan",
        "",
        "Source of truth: `requirements/*.md`.",
        "",
        "## Current Known Context",
        "",
    ]
    for name, lines in known.items():
        content.append(f"### {name.replace('_', ' ').title()}")
        content.extend(lines or ["- Missing."])
        content.append("")
    content.extend(_render_blueprint_plan_markdown(blueprint_plan))
    content.extend(
        [
            "## Drift Prevention",
            "",
            "- Chart/dashboard generation must read this requirements workspace before implementation.",
            "- User corrections go to `user_decisions.md` and `change_log.md`.",
            "- Missing requirements must produce a targeted question, not an invented assumption.",
            "",
        ]
    )
    write_text(req / "implementation_plan.md", "\n".join(content))
    return {"ok": True, "path": "requirements/implementation_plan.md", "known": {key: len(value) for key, value in known.items()}}


def build_dashboard_blueprint_plan(
    project_root: str | Path,
    *,
    update_plan: bool = True,
    source_text: str = "",
) -> dict[str, Any]:
    root = Path(project_root)
    req = root / "requirements"
    if not req.is_dir():
        initialize_requirements_workspace(project_root)
    text = source_text or read_persisted_source_requirement_text(project_root)
    selection = select_dashboard_blueprint(text)
    chart_plan = []
    negative_requirements = load_negative_requirement_ledger(root)
    for family in selection["recommended_chart_families"]:
        spec = get_chart_param_spec(family)
        decision = decide_chart(
            chart_id=f"{selection['dashboard_type']}_{spec.family}",
            business_question=text,
            dashboard_type=selection["dashboard_type"],
            user_decisions=_last_nonempty_lines(read_text(req / "user_decisions.md"), 8),
            negative_requirements=negative_requirements,
            requested_family=spec.family,
            source_evidence_refs=["requirements_workspace"],
        )
        chart_item = {
            "family": spec.family,
            "route": spec.route,
            "intent": spec.intent,
            "required_parameters": list(spec.required_parameters),
            "fallback_family": spec.fallback_family,
            "chart_decision_record": decision.to_dict(),
        }
        chart_plan.append(
            apply_decision_contract_to_chart_plan(root, chart_item)["chart_plan"]
        )
    source_inputs = read_text(req / "source_inputs.md")
    critical_questions = _critical_requirement_questions(source_inputs or text)
    plan = {
        "schema_version": "2026-07-13.requirements_dashboard_blueprint_plan.v2",
        "dashboard_type": selection["dashboard_type"],
        "confidence": selection["confidence"],
        "reason": selection["reason"],
        "job_to_be_done": selection["job_to_be_done"],
        "recommended_layout": selection["recommended_layout"],
        "selector_filter_behavior": selection["selector_filter_behavior"],
        "navigation_relations": selection["navigation_relations"],
        "acceptance_checklist": selection["acceptance_checklist"],
        "operational_lifecycle": selection["operational_lifecycle"],
        "conditional_ux_acceptance": selection["conditional_ux_acceptance"],
        "chart_plan": chart_plan,
        "critical_questions": critical_questions,
        "execution_blocked": bool(critical_questions),
        "block_reason": "missing_required_requirements" if critical_questions else "",
    }
    if update_plan:
        update_implementation_plan(project_root)
    return plan


def summarize_implementation_plan(project_root: str | Path) -> dict[str, Any]:
    initialize_requirements_workspace(project_root)
    text = read_text(Path(project_root) / "requirements" / "implementation_plan.md")
    return {"ok": True, "path": "requirements/implementation_plan.md", "summary": text[:6000]}


def validate_chart_plan_against_requirements(
    project_root: str | Path,
    *,
    chart_plan: dict[str, Any],
) -> dict[str, Any]:
    initialize_requirements_workspace(project_root)
    root = Path(project_root)
    combined = "\n".join(read_text(root / "requirements" / name).lower() for name in REQUIREMENTS_FILES)
    decision_record = chart_plan.get("chart_decision_record") or (
        chart_plan if chart_plan.get("schema_version") == "2026-06-30.dataviz_chart_decision.v1" else None
    )
    if decision_record is None:
        negative_requirements = load_negative_requirement_ledger(root)
        decision = decide_chart(
            chart_id=str(chart_plan.get("chart_id") or "chart_plan_validation"),
            business_question=read_persisted_source_requirement_text(root) or str(chart_plan),
            dashboard_type=str(chart_plan.get("dashboard_type") or "unknown"),
            negative_requirements=negative_requirements,
            requested_family=str(chart_plan.get("family") or chart_plan.get("selected_family") or ""),
            source_evidence_refs=["requirements_workspace"],
        )
        decision_record = decision.to_dict()
    decision_validation = validate_chart_decision_record(decision_record)
    decision_contract_issues = decision_contract_drift_issues(root, chart_plan)
    checks = []
    for key in ("metrics", "fields", "selectors", "charts"):
        for item in chart_plan.get(key) or []:
            value = str(item).strip()
            if value:
                checks.append({"kind": key, "value": value, "present": value.lower() in combined})
    missing = [item for item in checks if not item["present"]]
    return {
        "ok": not missing and decision_validation["ok"] and not decision_contract_issues,
        "chart_decision_record": decision_record,
        "decision_validation": decision_validation,
        "checks": checks,
        "missing": missing,
        "decision_contract_issues": decision_contract_issues,
        "question": _targeted_question(missing, combined)
        if missing
        else "; ".join([*decision_validation["issues"], *decision_contract_issues]),
    }


def read_persisted_requirements_text(project_root: str | Path) -> str:
    root = Path(project_root)
    req = root / "requirements"
    if not req.is_dir():
        return ""
    parts = []
    for name in (
        "dashboard_requirements.md",
        "dashboard_map.md",
        "dashboard_canvas.md",
        "metrics.md",
        "fields.md",
        "charts.md",
        "selectors.md",
        "object_relations.md",
        "user_decisions.md",
    ):
        parts.append(read_text(req / name))
    return "\n".join(parts).strip()


def read_persisted_source_requirement_text(project_root: str | Path) -> str:
    root = Path(project_root)
    req = root / "requirements"
    if not req.is_dir():
        return ""
    parts = []
    for name in (
        "source_inputs.md",
        "s2t.md",
        "data_architecture.md",
        "datasets.md",
        "connectors.md",
        "fields.md",
        "metrics.md",
        "dashboard_requirements.md",
        "dashboard_pages.md",
        "charts.md",
        "selectors.md",
        "object_relations.md",
        "user_decisions.md",
    ):
        parts.append(read_text(req / name))
    return "\n".join(parts).strip()


def _write_map_canvas_blueprint(
    root: Path,
    *,
    source_text: str,
    source_name: str,
    data_profile: dict[str, Any] | None = None,
) -> dict[str, Any]:
    selection = select_dashboard_blueprint(source_text, data_profile=data_profile)
    req = root / "requirements"
    map_block = _render_dashboard_map_block(selection, source_name=source_name)
    canvas_block = _render_dashboard_canvas_block(selection, source_name=source_name)
    write_text(req / "dashboard_map.md", read_text(req / "dashboard_map.md") + "\n" + map_block)
    write_text(req / "dashboard_canvas.md", read_text(req / "dashboard_canvas.md") + "\n" + canvas_block)
    return selection


def _render_dashboard_map_block(selection: dict[str, Any], *, source_name: str) -> str:
    return "\n".join(
        [
            f"## Blueprint Selection From {source_name}",
            "",
            f"- Dashboard type: `{selection['dashboard_type']}`",
            f"- Confidence: `{selection['confidence']}`",
            f"- Matched keywords: {', '.join(selection['matched_keywords']) or 'none'}",
            f"- System job: {selection['job_to_be_done']}",
            f"- Blueprint reason: {selection['reason']}",
            f"- Recommended charts: {', '.join(f'`{item}`' for item in selection['recommended_chart_families'])}",
            f"- Navigation/relations: {selection['navigation_relations']}",
            f"- Operational lifecycle required: `{str(selection['operational_lifecycle']['required']).lower()}`",
            f"- Operational lifecycle fields: {', '.join(selection['operational_lifecycle']['fields']) or 'not applicable'}",
            "",
        ]
    )


def _render_dashboard_canvas_block(selection: dict[str, Any], *, source_name: str) -> str:
    return "\n".join(
        [
            f"## Canvas Blueprint From {source_name}",
            "",
            f"- Dashboard type: `{selection['dashboard_type']}`",
            f"- Layout: {selection['recommended_layout']}",
            f"- Selector/filter behavior: {selection['selector_filter_behavior']}",
            f"- Expected interactivity: {selection['expected_interactivity']}",
            "- Required inputs/questions:",
            *[f"  - {item}" for item in selection["required_inputs_questions"]],
            "- Acceptance checklist:",
            *[f"  - {item}" for item in selection["acceptance_checklist"]],
            "- Conditional UX acceptance:",
            *(
                [
                    f"  - {condition['condition_id']}: {', '.join(condition['acceptance_checklist'])}"
                    for condition in selection["conditional_ux_acceptance"]["conditions"]
                ]
                or ["  - not applicable"]
            ),
            "- Native title/hint rule: chart titles and hints stay in DataLens dashboard/widget metadata.",
            "",
        ]
    )


def _append_chart_catalog(root: Path, *, source_text: str, source_name: str, selection: dict[str, Any]) -> None:
    req = root / "requirements"
    metrics = _catalog_terms(source_text, ("metric", "kpi", "measure"), fallback="<METRIC_NAME>")
    dimensions = _catalog_terms(source_text, ("field", "dimension", "attribute", "cut"), fallback="<DIMENSION_FIELD>")
    filters = _catalog_terms(source_text, ("filter", "selector", "control"), fallback="<FILTER_FIELD>")
    selectors = _catalog_terms(source_text, ("selector", "filter", "control"), fallback="<SELECTOR_PARAM>")
    critical = _critical_requirement_questions(source_text)
    status = "blocked_questions" if critical else "planned"
    lines = [
        f"## Chart Catalog From {source_name}",
        "",
        (
            "| Chart | Route | Dataset | Metrics | Dimensions | Filters | Selectors | "
            "Native title | Native hint | Source requirement | Status |"
        ),
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for index, family in enumerate(selection["recommended_chart_families"], start=1):
        spec = get_chart_param_spec(family)
        chart_key = f"{_slug(source_name)}_chart_{index:02d}"
        lines.append(
            "| "
            + " | ".join(
                [
                    f"`{chart_key}`",
                    f"`{spec.route}`",
                    "`<DATASET_ID>`",
                    metrics,
                    dimensions,
                    filters,
                    selectors,
                    f"`<NATIVE_TITLE:{spec.family}>`",
                    "`<NATIVE_HINT>`",
                    f"`{source_name}`",
                    f"`{status}`",
                ]
            )
            + " |"
        )
    if critical:
        lines.extend(["", "### Blocking Questions", *[f"- {question}" for question in critical]])
    lines.append("")
    write_text(req / "charts.md", read_text(req / "charts.md") + "\n" + "\n".join(lines))


def _append_object_relation_placeholders(
    root: Path,
    *,
    source_text: str,
    source_name: str,
    selection: dict[str, Any],
) -> None:
    req = root / "requirements"
    selectors = _catalog_terms(source_text, ("selector", "filter", "control"), fallback="<SELECTOR_PARAM>")
    first_family = selection["recommended_chart_families"][0] if selection["recommended_chart_families"] else "table_node"
    lines = [
        f"## Relation Plan From {source_name}",
        "",
        "| Selector | Target chart | Dataset | Fields | Native title/hint | Status |",
        "| --- | --- | --- | --- | --- | --- |",
        (
            f"| {selectors} | `{_slug(source_name)}_chart_01` | `<DATASET_ID>` | `<FIELD_LIST>` | "
            f"`<NATIVE_TITLE:{first_family}>` / `<NATIVE_HINT>` | `planned_placeholder` |"
        ),
        "",
        (
            "- Selector targets, chart ids, and dataset ids remain placeholders "
            "until the user chooses local-only project state or live readback supplies ids."
        ),
        "- Chart titles and hints stay in DataLens dashboard/widget metadata.",
        "",
    ]
    write_text(req / "object_relations.md", read_text(req / "object_relations.md") + "\n" + "\n".join(lines))


def _extract_requirement_lines(markdown_text: str) -> dict[str, list[str]]:
    buckets = {
        "data_architecture.md": [],
        "datasets.md": [],
        "connectors.md": [],
        "fields.md": [],
        "metrics.md": [],
        "dashboard_pages.md": [],
        "charts.md": [],
        "selectors.md": [],
        "object_relations.md": [],
        "dashboard_map.md": [],
        "dashboard_canvas.md": [],
    }
    for record in _requirement_records(markdown_text):
        line = record["text"]
        lowered = line.lower()
        matched: set[str] = set()
        for file_name, terms in REQUIREMENT_KEYWORDS.items():
            if any(term in lowered for term in terms):
                matched.add(file_name)
        header_text = " | ".join(record["headers"]).lower()
        if header_text:
            for file_name, terms in TABLE_HEADER_HINTS.items():
                if any(term in header_text for term in terms):
                    matched.add(file_name)
        rendered = f"- {line}"
        for file_name in matched:
            if rendered not in buckets[file_name]:
                buckets[file_name].append(rendered)
    return buckets


def _requirement_records(markdown_text: str) -> list[dict[str, Any]]:
    """Return prose and Markdown-table rows with table-header provenance.

    Dashboard requirement documents are often exported as pipe tables. Treating them as
    ordinary lines either loses the row entirely or matches only an incidental
    English token. Header-qualified records keep chart, metric, source, field,
    and tab meaning attached to every row without copying storage-format HTML.
    """

    records: list[dict[str, Any]] = []
    current_headers: list[str] = []
    for raw_line in markdown_text.splitlines():
        stripped = raw_line.strip()
        if not stripped:
            current_headers = []
            continue
        if stripped.startswith("|") and stripped.endswith("|"):
            cells = [cell.strip() for cell in stripped.strip("|").split("|")]
            if not cells or _is_markdown_separator_row(cells):
                continue
            if _looks_like_requirement_table_header(cells):
                current_headers = cells
                continue
            if not current_headers and len(cells) >= 2 and not any(cell for cell in cells[1:]):
                # Empty key/value rows such as ``Main contact |`` are not
                # evidence that the corresponding requirement was supplied.
                continue
            if current_headers and len(current_headers) == len(cells):
                parts = [
                    f"{header}: {value}"
                    for header, value in zip(current_headers, cells, strict=True)
                    if header and value
                ]
                text = " | ".join(parts)
            else:
                text = " | ".join(cell for cell in cells if cell)
            if text:
                records.append({"text": text, "headers": list(current_headers), "cells": cells, "kind": "table_row"})
            continue
        current_headers = []
        line = stripped.strip(" \t-")
        if line and not line.startswith("#"):
            records.append({"text": line, "headers": [], "cells": [], "kind": "line"})
    return records


def _is_markdown_separator_row(cells: list[str]) -> bool:
    return bool(cells) and all(re.fullmatch(r":?-{3,}:?", cell.replace(" ", "")) for cell in cells)


def _looks_like_requirement_table_header(cells: list[str]) -> bool:
    header_terms = {
        "№",
        "source",
        "dataset",
        "table",
        "field",
        "metric",
        "chart",
        "use case",
        "visualization type",
        "tab / order",
        "description",
        "источник",
        "витрина",
        "таблица",
        "поле",
        "метрика",
        "показатель",
        "чарт",
        "визуализация",
        "описание",
        "комментарий",
        "правило",
    }
    normalized = [" ".join(cell.lower().split()) for cell in cells]
    first = normalized[0] if normalized else ""
    first_header_cells = {
        "№",
        "#",
        "source",
        "dataset",
        "table",
        "field",
        "metric",
        "chart",
        "rule",
        "источник",
        "витрина",
        "таблица",
        "поле",
        "метрика",
        "чарт",
        "правило",
    }
    matches = sum(1 for cell in normalized if any(term == cell or term in cell for term in header_terms))
    if first in first_header_cells:
        return matches >= 2 or first in {"№", "#"}
    # Exported requirement tables often omit a numeric/id column and begin directly with
    # ``chart / use case`` or its Russian equivalent. Require a real multi-cell
    # table plus at least two semantic header cells so ordinary two-column
    # key/value rows are not reclassified as table headers.
    return len(normalized) >= 3 and matches >= 2


def _requirement_table_diagnostics(markdown_text: str) -> dict[str, Any]:
    issues: list[dict[str, str]] = []
    chart_rows = 0
    metric_rows = 0
    source_rows = 0
    for record in _requirement_records(markdown_text):
        headers = [" ".join(str(item).lower().split()) for item in record["headers"]]
        cells = [str(item).strip() for item in record["cells"]]
        if not headers or len(headers) != len(cells):
            continue
        header_text = " | ".join(headers)
        row_id = cells[0] or f"row_{chart_rows + metric_rows + source_rows + 1}"
        is_chart_row = any(term in header_text for term in ("chart", "use case", "visualization type", "чарт", "визуализация"))
        is_metric_row = not is_chart_row and any(
            term in header_text for term in ("metric", "kpi", "measure", "formula", "метрик", "показател", "формул", "расчет", "расчёт")
        )
        is_source_row = not is_chart_row and any(
            term in header_text for term in ("source", "dataset", "table", "источник", "витрина", "таблица")
        )
        if is_chart_row:
            chart_rows += 1
            for field_name, terms in (
                ("chart_or_use_case", ("chart", "use case", "чарт")),
                ("visualization_type", ("visualization type", "тип визуализац")),
                ("metric", ("metrics", "metric", "kpi", "метрик", "показател")),
                ("field_or_source", ("fields", "source", "поля", "источник")),
            ):
                if not _table_cell_value(headers, cells, terms):
                    issues.append(_missing_brd_cell(row_id, field_name))
        elif is_metric_row:
            metric_rows += 1
            for field_name, terms in (
                ("metric", ("metric", "kpi", "measure", "метрик", "показател")),
                ("formula", ("formula", "calculation", "формул", "расчет", "расчёт")),
                ("source", ("source", "dataset", "table", "источник", "витрина", "таблица")),
            ):
                if any(any(term in header for term in terms) for header in headers) and not _table_cell_value(headers, cells, terms):
                    issues.append(_missing_brd_cell(row_id, field_name))
        elif is_source_row:
            source_rows += 1
    return {
        "ok": not issues,
        "chart_row_count": chart_rows,
        "metric_row_count": metric_rows,
        "source_row_count": source_rows,
        "blocking_issue_count": len(issues),
        "issues": issues,
    }


def _table_cell_value(headers: list[str], cells: list[str], terms: tuple[str, ...]) -> str:
    matched = False
    for header, value in zip(headers, cells, strict=True):
        if any(term in header for term in terms):
            matched = True
            if value.strip():
                return value.strip()
    if matched:
        return ""
    return ""


def _missing_brd_cell(row_id: str, field_name: str) -> dict[str, str]:
    return {
        "severity": "error",
        "category": "missing_required_brd_cell",
        "row_id": row_id,
        "field": field_name,
        "question": f"Confirm {field_name} for BRD row {row_id}.",
    }


def _render_blueprint_plan_markdown(plan: dict[str, Any]) -> list[str]:
    lines = [
        "## Dashboard Blueprint",
        "",
        f"- Type: `{plan['dashboard_type']}`",
        f"- Confidence: `{plan['confidence']}`",
        f"- Reason: {plan['reason']}",
        f"- Job-to-be-done: {plan['job_to_be_done']}",
        f"- Layout: {plan['recommended_layout']}",
        f"- Selector/filter behavior: {plan['selector_filter_behavior']}",
        f"- Navigation/relations: {plan['navigation_relations']}",
        f"- Operational lifecycle required: `{str(plan['operational_lifecycle']['required']).lower()}`",
        f"- Operational lifecycle fields: {', '.join(plan['operational_lifecycle']['fields']) or 'not applicable'}",
        f"- Conditional UX rules: {', '.join(item['condition_id'] for item in plan['conditional_ux_acceptance']['conditions']) or 'none'}",
        "",
        "### Draft Chart Plan",
    ]
    for item in plan["chart_plan"]:
        lines.append(
            f"- `{item['family']}` via `{item['route']}` for `{item['intent']}`; "
            f"required params: {', '.join(item['required_parameters'])}; fallback `{item['fallback_family']}`."
        )
    lines.extend(["", "### Critical Questions"])
    lines.extend([f"- {question}" for question in plan["critical_questions"]] or ["- None."])
    if plan.get("execution_blocked"):
        lines.extend(["", "- Execution blocked: missing required requirements."])
    lines.append("")
    return lines


def _catalog_terms(text: str, keywords: tuple[str, ...], *, fallback: str) -> str:
    values: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.strip(" \t-")
        if not line:
            continue
        lowered = line.lower()
        if any(keyword in lowered for keyword in keywords):
            values.append(_strip_table_separators(line))
    return "<br>".join(values[:4]) if values else f"`{fallback}`"


def _strip_table_separators(value: str) -> str:
    return value.replace("|", "/").strip()


def _slug(value: str) -> str:
    slug = "".join(ch.lower() if ch.isalnum() else "_" for ch in value)
    return "_".join(part for part in slug.split("_") if part) or "source"


def _critical_requirement_questions(text: str) -> list[str]:
    lowered = _requirement_signal_text(text).lower()
    questions: list[str] = []
    if not any(
        term in lowered
        for term in (
            "audience",
            "users",
            "owner",
            "stakeholder",
            "primary users",
            "аудитор",
            "пользовател",
            "владелец",
            "заказчик",
            "стейкхолдер",
            "основной контакт",
        )
    ):
        questions.append("Who is the audience and owner for this dashboard?")
    if not any(
        term in lowered
        for term in (
            "decision",
            "action",
            "job-to-be-done",
            "take action",
            "alert",
            "rollout",
            "решен",
            "действ",
            "назначен",
            "use case",
            "проверить",
            "оценить",
            "показать",
            "понять",
            "найти",
        )
    ):
        questions.append("Which decision or action should the dashboard support?")
    if not any(term in lowered for term in ("metric", "kpi", "measure", "метрик", "показател", "формул", "расчет", "расчёт")):
        questions.append("Which KPI or metric definitions are accepted?")
    if not any(
        term in lowered
        for term in ("freshness", "source", "dataset", "connector", "table", "свежест", "источник", "витрин", "датасет", "таблиц")
    ):
        questions.append("Which data source and freshness expectation are accepted?")
    if not any(
        term in lowered
        for term in ("quality", "dq", "caveat", "risk", "качеств", "риск", "ограничен", "no table", "no data")
    ):
        questions.append("Which data quality risks or caveats must be visible?")
    lifecycle = select_dashboard_blueprint(lowered)["operational_lifecycle"]
    if lifecycle["required"]:
        if not any(
            term in lowered
            for term in ("support", "feedback", "help channel", "поддерж", "обратн", "канал связи")
        ):
            questions.append("Who owns the dashboard product and the support or feedback channel?")
        if not any(
            term in lowered
            for term in (
                "usage analytics",
                "usage tracking",
                "privacy-limited",
                "аналитика использования",
                "сбор статистики",
            )
        ):
            questions.append("Is Usage Analytics enabled, disabled, or privacy-limited for this dashboard?")
        if not any(
            term in lowered
            for term in (
                "adoption metric",
                "usage metric",
                "review cadence",
                "monthly review",
                "weekly review",
                "метрика использования",
                "востребован",
                "ритм ревью",
            )
        ):
            questions.append("Which adoption metric is reviewed, and on what cadence?")
        if not any(
            term in lowered
            for term in ("performance", "latency", "error threshold", "slo", "sla", "производительн", "задержк", "порог ошибок")
        ):
            questions.append("Which performance, error, and data-freshness thresholds trigger action?")
        if not any(
            term in lowered
            for term in ("deprecation", "retirement", "promotion", "expiry", "sunset", "вывод из эксплуатации", "устареван", "срок жизни")
        ):
            questions.append("What are the promotion, deprecation, and retirement rules?")
    questions.extend(issue["question"] for issue in _requirement_table_diagnostics(text)["issues"])
    return list(dict.fromkeys(questions))


def _requirement_signal_text(text: str) -> str:
    ignored = {"missing.", "source of truth: `requirements/*.md`."}
    lines = []
    for record in _requirement_records(text):
        compact = str(record["text"]).strip()
        if not compact or compact.lower() in ignored:
            continue
        lowered = compact.lower()
        if compact.endswith("?"):
            continue
        if "<" in compact and ">" in compact:
            continue
        if lowered.startswith("execution blocked:"):
            continue
        if lowered in {"blocking questions", "critical questions"}:
            continue
        lines.append(compact)
    return "\n".join(lines)


def _append_change(root: Path, text: str) -> None:
    path = root / "requirements" / "change_log.md"
    write_text(path, read_text(path) + f"| {_timestamp()} | {text} |\n")


def _last_nonempty_lines(text: str, limit: int) -> list[str]:
    lines = [line for line in text.splitlines() if line.strip() and not line.startswith("#")]
    return lines[-limit:]


def _targeted_question(missing: list[dict[str, Any]], combined: str) -> str:
    first = missing[0]
    known = "requirements workspace has recorded context" if combined.strip() else "requirements workspace is empty"
    return (
        f"Missing {first['kind']} requirement `{first['value']}`; {known}. "
        "Please provide or confirm this requirement before chart generation."
    )


def _timestamp() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
