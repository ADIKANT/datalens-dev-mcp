---
name: datalens-editor
description: Use when authoring or diagnosing DataLens JavaScript Editor table, Gravity, Advanced, Markdown, selector charts, or HTML inside an Editor chart. Not for standalone HTML Pages, native Wizard charts, or independent SDK scripts.
---

# DataLens Editor

For discovery or new creation in an explicit workbook, start with that workbook's actual inventory and Editor subtype/renderer. If a suitable example is missing, inspect the business workspace's root navigation and only relevant project `AGENTS.md`/`CONTEXT.md` files; confirm a candidate's live ID and type. A Wizard-only project does not establish that Editor is unavailable. When creation is authorized, use a supported recipe or local example to create an Editor in the requested workbook, remapping aliases and dependencies to authorized objects or read-only sources. Verify actual container membership before writing; dependencies do not expand mutation scope.

Work from the exact dashboard project/subproject. For a single-tab edit, read that target in full, patch only the requested tab, and verify the changed behavior; do not recompile the entire chart or traverse its workbook. Read [Editor authoring](references/editor-authoring.md) for the actual runtime variant (`table_node`, `d3_node`, `advanced-chart_node`, `markdown_node` or `control_node`). Preserve that technology, untouched tabs, Meta aliases and source bindings. Diagnose missing aliases, upstream errors and valid empty results separately.

Use `dl_compile_recipe` for registered visual families, adjusting bindings and permitted presentation values. Its compact `draft_reference` addresses the complete private draft: pass it to validation/create; for update combine its `artifact_path` with exact target identity and fresh revision. Reuse packaged renderers rather than reproducing their JavaScript.

`dl_editor_validate` checks static tabs, aliases and constrained-runtime rules. Verify changed runtime/visual behavior in Browser separately. HTML generated inside an Editor/table cell follows that Editor contract; standalone Page CSP and host messaging do not apply.

Follow [authorized scope and delivery](../datalens-dashboard/references/authorized-scope.md) and, for a visual/semantic change, the relevant [visualization decision](../datalens-dashboard/references/decision-quality.md). Route Wizard to `datalens-dataset-wizard`, placement to `datalens-dashboard`, discovery to `datalens-inspect`, and standalone Page/backup/cleanup to `datalens-maintenance`.
