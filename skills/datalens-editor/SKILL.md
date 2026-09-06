---
name: datalens-editor
description: Author and diagnose DataLens JavaScript Editor table, Gravity, Advanced, Markdown, and selector charts using supported tabs and runtimes.
---

# DataLens Editor

Read [references/editor-authoring.md](references/editor-authoring.md) before compiling or validating Editor objects.

Select the actual Editor variant (`table_node`, `d3_node`, `advanced-chart_node`, `markdown_node`, or `control_node`) and preserve it on update. Use `dl_compile_recipe` for a registered visual family so the canonical renderer is reused; change bindings and allowed presentation values instead of regenerating large JavaScript. Use `dl_editor_validate` for static tabs, aliases and constrained-runtime checks. Report browser/live evidence separately.

Preserve the existing Editor technology. Resolve declared Meta aliases, Sources, Prepare, Config, Controls, Params, and wrapped render functions according to the selected chart type. Use packaged reusable recipes for repeated visual families; do not regenerate their large JavaScript implementation for each task.
