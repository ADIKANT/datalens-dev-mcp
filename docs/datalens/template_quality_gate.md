# Template Quality Gate

This gate keeps chart creation template-based and route-bounded. It applies to
the local MCP runtime, generated project artifacts, and committed examples.

## Supported Creation Routes

Chart creation is limited to `wizard_native`, registered Editor routes, and
explicit-only `ql_explicit`. Standard charts use Wizard. Advanced Editor is
used by direct request or a capability gap; `editor_table`, `editor_markdown`,
and `editor_js_control` keep their specialized contracts.

QL create/update may appear only after a direct QL request with an explicit
payload or fresh saved seed. Automatic QL selection, QL prompt
generation, and `deleteQLChart` remain forbidden.

## Template Coverage

- Every family in the supported chart registry must be present in
  `templates/datalens/standard_chart_templates.json`.
- Every registered family must point to an existing template directory with
  `README.md`, `schema.json`, `example_input.json`, and all route-required JS
  files.
- Every removed family in `REMOVED_CHARTS` must be absent from the registry.
  Removed requests route to a supported alternative or a targeted question.
- Unknown chart requests return a structured question/fallback. They do not
  invent a chart family or generate ad hoc JS.

## Advanced Editor JavaScript

Advanced templates must:

- Use `Editor.wrapFn` and return HTML through `Editor.generateHtml`.
- Use committed shared helpers and style tokens.
- Normalize source rows before render.
- Keep dashboard/widget title and hint in native metadata unless a Markdown or
  text widget explicitly needs visible body text.
- Include comment blocks for source/data, params/config, prepare/model,
  render, layout, labels/tooltips, theme, interactions, and extension points.
- Preserve signed numeric domains for time, comparison, distribution, and
  relationship renderers. Part-to-whole and flow semantics reject invalid
  negative or missing values instead of emitting misleading geometry.
- Pass `node -c` syntax checks.

## Table, Markdown, And Control Routes

These routes are intentional and route-native:

- `editor_table` returns `head` and `rows`; it does not create custom HTML.
- `editor_markdown` returns Markdown content; dashboard layout owns placement.
- `editor_js_control` returns native control definitions; selector targets are
  recorded in dashboard relation artifacts.

All three routes inherit DataLens light/dark theme behavior and must keep
selector layout defaults aligned with local config: left labels, percentage
widths, and a 94 percent selector row budget.

Production selectors must preserve the explicit `selector_contract` and family
semantics. Static selects require caller-owned options, dynamic selects require
a real source binding, and date ranges use the official `range-datepicker`
contract with either one interval parameter or a complete from/to parameter
pair. Missing contracts block with empty controls and Params; requirements text
is not used to invent parameters or options. Every Params value must be an array
of strings. Production Markdown requires explicit content except for a section
header that can be derived entirely from its supplied title.

## Wizard Native Templates

All templates in `templates/datalens/wizard/canonical_templates.json` must
compile without private IDs and pass visualization/role validation. New
compiler inputs with known field types enforce numeric measure/size and
geographic role compatibility. Saved readback still reports a type mismatch,
but an update blocks on it only when the action explicitly owns a numeric or
geographic semantic-policy change; unchanged valid DataLens bindings are
preserved. Seed tests reject stale, wrong-branch, and mismatched visualization
inputs. Maps require geo evidence and bubble requires size.

## Relation And Metadata Gate

Generated dashboard plans must validate:

- native title and hint metadata;
- selector target bindings for every declared parameter, including both
  parameters of a paired date range;
- tab/chart references;
- percentage widths and a 94 percent selector row budget;
- chart relation endpoints;
- navigation endpoints.

## Verification Commands

```bash
python3 -m unittest tests.unit.test_standard_chart_templates tests.unit.test_template_quality_gate tests.unit.test_chart_routing_wizard_js_only tests.unit.test_advanced_templates_parameterization -v
python3 -m unittest tests.unit.test_dashboard_object_relations tests.unit.test_dashboard_layout_contract -v
python3 scripts/run_visual_runtime_contract_sweep.py --strict
```

If Node.js is available, the gate also executes 450 compact-to-wide renderer
probes across all 25 registered Advanced Editor families, combining six widths
with three independent heights.
