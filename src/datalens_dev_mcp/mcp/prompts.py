from __future__ import annotations

CORE_DIRECTIVE = (
    "Core: object route before chart; templates-first; no removed chart routes; Wizard path is separate; "
    "use the standard registry; obey Advanced Editor and never invent methods; "
    "use VisualDecisionEngine, RendererVisualSpec, and negative requirements; "
    "use strict_dashboard for registered Editor families; persistent Markdown requirements; "
    "delivery intent before writes; one fresh scoped baseline; batch generation with artifact summaries; "
    "clear blockers; no legacy cache sync. "
)


def _core(text: str) -> str:
    return CORE_DIRECTIVE + text


PROMPTS: dict[str, dict[str, str]] = {
    "datalens.develop_dashboard": {
        "description": "One-prompt lane for a new governed dashboard from requirements and data evidence.",
        "text": _core(
            "Develop from persisted requirements and one scoped target baseline. "
            "Call dl_generate_editor_bundle once with all widgets in chart_specs, validate locally, and build the safe-apply plan. "
            "For implementation, call dl_execute_safe_apply once; it owns save, both readbacks, and publish-from-saved. "
            "Use publish-plan only to resume a stopped run and use one generated browser QA pass."
        ),
    },
    "datalens.redesign_existing": {
        "description": "Hydrate an existing dashboard baseline, redesign safely, and produce review artifacts.",
        "text": _core(
            "Redesign the existing DataLens dashboard. Use supplied context_ref and remote baseline, "
            "preserve unknown fields, build governed chart decisions, generate Editor bundles, validate, "
            "produce dry-run payloads and a safe-apply plan. An explicit redesign request continues through save and "
            "publish; plan-only, save-only, and no-publish wording limits that flow."
        ),
    },
    "datalens.enhance_existing": {
        "description": "Add or repair widgets/selectors on an existing dashboard with fresh-read gates.",
        "text": _core(
            "Enhance the existing DataLens dashboard. Use readback/baseline resources, keep existing links "
            "and revisions, generate only scoped changes, validate route contracts, and require safe apply."
        ),
    },
    "datalens.wizard_to_js": {
        "description": "Classify Wizard widgets, preserve native maps, and plan supported JS conversions.",
        "text": _core(
            "Plan an explicitly requested technology conversion. Hydrate fresh saved evidence, preserve existing Wizard "
            "visualizations by default, use editor_advanced only for registered capability gaps, keep dedicated Markdown/control "
            "routes, and mark ambiguous conversions for manual review."
        ),
    },
    "datalens.safe_apply_review": {
        "description": "Review a dry-run payload and safe-apply plan before any guarded write.",
        "text": _core(
            "Review the safe-apply plan. Check that runtime writes are enabled and the plan is bound to the current request, "
            "fresh reads preserve revisions and unknown fields, mode is save, no delete/move exists, "
            "publish actions use saved-readback source, and saved plus published readback reports will be produced."
        ),
    },
    "datalens.visual_review": {
        "description": "Review a DataLens dashboard or widget using local governance rules.",
        "text": _core(
            "Use the local DataLens governance docs, style guide, routing model, and dashboard evidence. "
            "Return pass/fail findings tied to "
            "business question, route, chart family, layout, selector behavior, and required fixes."
        ),
    },
    "datalens.widget_conversion": {
        "description": "Plan or implement a governed non-map widget conversion to supported Editor routes.",
        "text": _core(
            "Use the local route contract, implementation rules, and safe-apply context. Preserve existing technology, "
            "route standard creates to Wizard, and keep Markdown/selectors on their dedicated Editor surfaces. Generate "
            "real tabs from gallery/templates, validate, and honor the user's delivery intent: implementation continues "
            "through guarded save/publish, while review or plan-only remains read-only."
        ),
    },
    "datalens.live_diagnostics": {
        "description": "Run read-only live DataLens diagnostics and prepare safe local evidence.",
        "text": _core(
            "Use read-only tools first: workbook entries, dashboard baseline, editor/wizard chart hydration, "
            "datasets, connections, and relations. Never print tokens. Preserve IDs and linkage evidence in "
            "local-only artifacts, then use safe-apply review before any save operation."
        ),
    },
}


def list_prompts() -> list[dict[str, str]]:
    return [
        {
            "name": name,
            "title": " ".join(part.capitalize() for part in name.removeprefix("datalens.").replace("_", " ").split()),
            "description": item["description"],
        }
        for name, item in PROMPTS.items()
    ]


def get_prompt(name: str) -> dict[str, object]:
    item = PROMPTS[name]
    return {
        "description": item["description"],
        "messages": [
            {
                "role": "user",
                "content": {"type": "text", "text": item["text"]},
            }
        ],
    }
