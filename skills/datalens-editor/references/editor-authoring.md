# Editor authoring

The five Editor variants have different contracts. Native JavaScript table uses `table_node` and Config; Gravity uses `d3_node`; Advanced uses `advanced-chart_node`; Markdown uses `markdown_node`; selectors use `control_node`. Do not route all JavaScript work to Advanced.

For first-pass visual work call `dl_authoring_defaults`, then `dl_compile_recipe` with typed bindings and presentation. Registered recipes own title, hint, tooltip, formatting, axes, labels, legend, comparison, geometry and states. Large renderer modules are packaged assets; do not reproduce them in prompts or output payloads. An explicit current requirement or reference has priority over project and user defaults.

Editor execution is source data, Prepare transformation, then rendering. Use valid source aliases and the exact tabs for the variant. Do not assume Node.js, `libs/sql/v1`, arbitrary npm packages, or browser APIs exist. Preserve arguments passed through `wrapFn`. A static check is reported as `static/source contract checked; live result not checked` until a real DataLens runtime read or host browser inspection proves the result.

Pure title, hint, spacing, color or layout changes do not require a Dataset query. A direct-source Editor chart must not receive a fictitious Dataset or a fabricated data-proof pass.
