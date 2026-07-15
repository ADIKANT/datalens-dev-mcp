# Model Response Examples

Source trace: chart decision matrix, parameter matrix, MCP response contracts, official API catalog, Wizard template registry, and requirements workflow.

## Requirements Ingestion

Input: "Build an experiment report for product owners with conversion KPI, cohorts, daily freshness, and rollout decision."

Expected response summary:

- Dashboard type: `experiment_report`.
- Draft chart plan: `kpi_value_delta`, `line_chart`, `grouped_bar`, `table_node`, `md_methodology_block`.
- Persisted files: `requirements/source_inputs.md`, `requirements/dashboard_map.md`, `requirements/dashboard_canvas.md`, `requirements/implementation_plan.md`.
- Critical questions: none if audience, action, metrics, source freshness, and data quality caveats are present.

## Dashboard Planning

- Type: `self_service`.
- Reason: filter-heavy detail request with many related questions.
- Layout: selector panel, summary, comparison/trend, detail table.
- Selector behavior: defaults, reset, dependencies, target widgets.
- Relation artifact: `artifacts/dashboard_object_relations.json`.

## Wizard Standard Chart

- Route: `wizard_native`.
- Visualization: `line` (or the mapped canonical ID).
- Selection origin: `wizard_first_default`.
- Template source: matching fresh saved seed, otherwise canonical template.
- Method: `createWizardChart`.
- Required evidence: location XOR, dataset ref, semantic field bindings, and
  role validation; geolayer additionally requires geo evidence.
- Next step: validate and safe-apply save; offline fixtures do not claim live verification.

## Advanced Editor JS

- Route: `editor_advanced`.
- Family: `line_chart`.
- Template: `templates/datalens/advanced_editor/time_series`.
- JS contract: `Editor.wrapFn` render lifecycle and `Editor.generateHtml`.
- Native title/hint: stored in dashboard/widget metadata and relation artifact.

## Dataset/Connector/Field

- Dataset/connector create/update: guarded plan-only with official method.
- Dataset schema read/validation: executable read-only.
- Standalone calculated field create: `unavailable_api_method`; use dataset update payload planning.

## Selector Relation

- Label placement: `left`.
- Width: percentage.
- Row total: `96%`.
- Targets: explicit widgets/charts only.

## Missing Input

- Status: `blocked_question`.
- Example: "Which business question, metric, dimension/date field, and intended action should this chart support?"

## Missing Credentials

- Status: `BLOCKED_LIVE_CREDENTIALS`.
- Retry: set credentials and run `dl_auth_probe`, then use the read-only discovery tools.

## Explicit QL Creation

- Route: `ql_explicit`.
- Status: guarded plan-only.
- Behavior: only a direct user QL request with an explicit payload or fresh
  saved QL seed can produce create/update planning.
  Vague SQL/chart requests never select QL and QL delete remains closed.
