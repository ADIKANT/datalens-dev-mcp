---
name: datalens-editor
description: Use when authoring or diagnosing DataLens JavaScript Editor table, Gravity, Advanced, Markdown, or selector charts.
---

# DataLens Editor

Read [references/editor-authoring.md](references/editor-authoring.md) before compiling or validating Editor objects.

Select the actual Editor variant (`table_node`, `d3_node`, `advanced-chart_node`, `markdown_node`, or `control_node`) and preserve it on update. Use `dl_compile_recipe` for a registered visual family so the canonical renderer is reused; change bindings and allowed presentation values instead of regenerating large JavaScript. The tool materializes the complete draft in private local state and returns a compact `draft_reference`; pass that reference directly to validation/create, or combine its `artifact_path` only with update target identity and fresh revision, instead of reading and echoing the renderer. Use `dl_editor_validate` for static tabs, aliases and constrained-runtime checks. Report browser/live evidence separately.

Preserve the existing Editor technology. Resolve declared Meta aliases, Sources, Prepare, Config, Controls, Params, and wrapped render functions according to the selected chart type. Use short Dataset or direct QL/API source bindings where applicable. Keep missing alias, upstream error, and a valid empty result distinct. Use packaged reusable recipes for repeated visual families; do not regenerate their large JavaScript implementation for each task.

Follow [authorized scope and delivery](../datalens-dashboard/references/authorized-scope.md) for mutations: explicit scoped work continues without repeated permission questions; read-only and save-only limits remain binding.

For new visual or semantic decisions, consult only the relevant part of [visualization decisions](../datalens-dashboard/references/decision-quality.md); preserve the accepted reference and infer routine context without a mandatory questionnaire.
