# Requirements Map Canvas Workflow

This project-authored workflow is implemented by
`config/datalens_dashboard_type_model.json` and the requirements pipeline.

## Intake

- User text and data profiles are persisted into `requirements/source_inputs.md` and role-specific requirement files.
- `ingest_requirements_markdown` extracts metrics, fields, selectors, object relations, Dashboard Map lines, and Dashboard Canvas lines.
- The same intake now selects a dashboard blueprint and appends structured Map/Canvas blocks.
- The same intake updates chart catalog and relation placeholder blocks before implementation.

## Dashboard Map

Map captures system context:

- roles and decision owners;
- objects, processes, states, handoffs, source systems, data quality risks;
- dashboards, priorities, owners, lifecycle, promotion/expiry rule;
- metrics, cuts, time grain, baselines, thresholds, freshness;
- connections, datasets, permissions, relations, and navigation targets.

## Dashboard Canvas

Canvas captures one dashboard:

- purpose, audience, job-to-be-done, success signal;
- scenarios, decisions, owners, and frequency;
- tables, joins, fields, metrics, freshness, data quality caveats;
- visual blocks with chart/control family, route, native title, native hint, and fallback;
- selectors, object relations, navigation targets, acceptance checklist.

## Runtime Flow

1. `dl_ingest_requirements_markdown` or `dl_ingest_requirements` persists the source text.
2. `select_dashboard_blueprint` selects `overview`, `self_service`, `object_management`, `alerts_mailing`, `analytical_tool`, `experiment_report`, or `project_ad_hoc`.
3. `populate_dashboard_map_canvas` writes the selected type, reason, layout, charts, filters, relations, questions, and checklist.
4. `update_implementation_plan` summarizes the latest Map/Canvas alongside metrics, fields, charts, selectors, relations, and decisions.
5. Chart generation reads the requirements workspace and chart parameter matrix before creating any Editor/Wizard plan.

## Guardrails

- Missing audience, business action, source freshness, metric definition, required fields, or object relations should produce a targeted question.
- Selectors must declare targets and reset/default behavior.
- Native DataLens title/hint standard is preserved.
- Dashboard planning does not execute writes; safe apply/readback is a later guarded stage.
