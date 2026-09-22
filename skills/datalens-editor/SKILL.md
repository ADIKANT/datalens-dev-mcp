---
name: datalens-editor
description: Use when authoring or diagnosing DataLens JavaScript Editor table, Gravity, Advanced, Markdown, selector charts, or HTML inside an Editor chart. Not for standalone HTML Pages, native Wizard charts, or independent SDK scripts.
---

# DataLens Editor

For a known Editor, start with that target's current identity, parent and subtype/renderer; no workbook-wide inventory is needed. Use inventory when selecting an unknown target or discovering a suitable existing example. If that evidence is insufficient, inspect the business workspace's root navigation and only relevant project `AGENTS.md`/`CONTEXT.md` files; confirm a candidate's live ID and type. A Wizard-only project does not establish that Editor is unavailable. For authorized creation, use a supported recipe or example in the requested workbook, remapping aliases and dependencies to authorized objects or read-only sources. Dependencies do not expand mutation scope.

Work from the exact dashboard project/subproject. For a single-tab edit, read that target in full, patch only the requested tab, and verify the changed behavior; do not recompile the entire chart or traverse its workbook. Read [Editor authoring](references/editor-authoring.md) for the actual runtime variant (`table_node`, `d3_node`, `advanced-chart_node`, `markdown_node` or `control_node`). Preserve that technology, untouched tabs, Meta aliases and source bindings. Diagnose missing aliases, upstream errors and valid empty results separately.

Use `dl_compile_recipe` for new registered visual families or a requested redesign, adjusting bindings and permitted presentation values. Its compact `draft_reference` addresses the complete private draft: pass it to validation/create; for update combine its `artifact_path` with exact target identity and fresh revision. A small existing-tab edit uses the observed tabs, not recipe compilation. Reuse packaged renderers rather than reproducing their JavaScript. New KPI/period/table recipes inherit widget title/hint ownership; pass a concrete `bindings.hint` and carry the resulting presentation into placement. Standalone pending placement does not create an internal replacement hint. Business labels, units and source IDs belong in bindings/project overrides.

`dl_editor_validate` checks static tabs, aliases and constrained-runtime rules. Verify changed runtime/visual behavior in Browser separately. HTML generated inside an Editor/table cell follows that Editor contract; standalone Page CSP and host messaging do not apply.

For period-series recipes, comparison must apply to the series: `comparison.enabled=false` disables it; an explicit `true` retains an unavailable state when previous data are missing. `legend.mode=hidden` hides the legend. Scope optional `tooltip.hide_null`, `tooltip.hide_zero_multi` and `legend.hide_empty_series` to the requested presentation; they do not change Dataset rows or share denominators. Follow the project's accepted profile and [visualization decisions](../datalens-dashboard/references/decision-quality.md); existing-tab changes still use a narrow patch.

Follow [authorized scope and delivery](../datalens-dashboard/references/authorized-scope.md) and, for a visual/semantic change, the relevant [visualization decision](../datalens-dashboard/references/decision-quality.md). Route Wizard to `datalens-dataset-wizard`, placement to `datalens-dashboard`, discovery to `datalens-inspect`, and standalone Page/backup/cleanup to `datalens-maintenance`.

For unknown effects follow [repeat-effect recovery](../datalens-dashboard/references/authorized-scope.md#unknown-outcomes-and-repeat-effects): only proven non-application or separate informed repeat authorization permits another attempt. Failed reconciliation, absent inventory and a new operation_id do not make a retry safe.
