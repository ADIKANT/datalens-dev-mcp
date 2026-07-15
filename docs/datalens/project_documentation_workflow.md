# Project Documentation Workflow

Every dashboard project gets a persistent local `requirements/` workspace. The
workspace is updated before implementation whenever new user input arrives.

## Required Files

- `requirements/source_inputs.md`
- `requirements/s2t.md`
- `requirements/data_architecture.md`
- `requirements/metrics.md`
- `requirements/dashboard_requirements.md`
- `requirements/dashboard_map.md`
- `requirements/dashboard_canvas.md`
- `requirements/implementation_plan.md`
- `requirements/charts.md`
- `requirements/object_relations.md`
- `requirements/user_decisions.md`
- `requirements/change_log.md`

The MCP also initializes supporting files for datasets, connectors, fields,
pages, and selectors because implementation usually needs them.

## Update Order

1. Persist source text in `source_inputs.md` and the role-specific file.
2. Extract obvious data architecture, metric, field, chart, selector, and
   relation lines.
3. Select a Dashboard Map/Canvas blueprint.
4. Append chart catalog rows.
5. Append selector/chart relation placeholders.
6. Record the change in `change_log.md`.
7. Refresh `implementation_plan.md`.

## Blocking Rules

Missing audience, decision/action, KPI definition, source/freshness, or data
quality context creates critical questions and sets `execution_blocked=true` in
the blueprint plan. Generation should ask the question instead of guessing.

## Id Policy

Use placeholders by default:

- `<DATASET_ID>`
- `<FIELD_LIST>`
- `<SELECTOR_PARAM>`
- `<NATIVE_TITLE:family>`
- `<NATIVE_HINT>`

Store source DataLens object ids only when the user explicitly chooses
local-only project state or live readback supplies them as part of an approved
workflow.
