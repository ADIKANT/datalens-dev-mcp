# Template Quality Gate

This gate keeps chart creation template-based and route-bounded. It applies to
the local MCP runtime, generated project artifacts, and committed examples.

## Approved Creation Routes

Chart creation is limited to `wizard_native`, registered Editor routes, and
explicit-only `ql_explicit`. Standard charts use Wizard. Advanced Editor is
used by direct request or a capability gap; `editor_table`, `editor_markdown`,
and `editor_js_control` keep their specialized contracts.

QL create/update may appear only with direct-request approval provenance and an
explicit payload or fresh saved seed. Automatic QL selection, QL prompt
generation, and `deleteQLChart` remain forbidden.

## Template Coverage

- Every family in `APPROVED_CHARTS` must be present in
  `templates/datalens/standard_chart_templates.json`.
- Every registered family must point to an existing template directory with
  `README.md`, `schema.json`, `example_input.json`, and all route-required JS
  files.
- Every removed family in `REMOVED_CHARTS` must be absent from the registry.
  Removed requests route to an approved alternative or a targeted question.
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
- Pass `node -c` syntax checks.

## Table, Markdown, And Control Routes

These routes are intentional and route-native:

- `editor_table` returns `head` and `rows`; it does not create custom HTML.
- `editor_markdown` returns Markdown content; dashboard layout owns placement.
- `editor_js_control` returns native control definitions; selector targets are
  recorded in dashboard relation artifacts.

All three routes inherit DataLens light/dark theme behavior and must keep
selector layout defaults aligned with local config: left labels, percentage
widths, and a 96 percent selector row total.

## Wizard Native Templates

All templates in `templates/datalens/wizard/canonical_templates.json` must
compile without private IDs and pass visualization/role validation. Seed tests
must reject stale, wrong-branch, and mismatched visualization inputs. Maps
require geo evidence and bubble requires size.

## Relation And Metadata Gate

Generated dashboard plans must validate:

- native title and hint metadata;
- selector target bindings;
- tab/chart references;
- percentage widths and 96 percent selector row total;
- chart relation endpoints;
- navigation endpoints.

## Verification Commands

```bash
python3 -m unittest tests.unit.test_standard_chart_templates tests.unit.test_template_quality_gate tests.unit.test_chart_routing_wizard_js_only tests.unit.test_advanced_templates_parameterization -v
python3 -m unittest tests.unit.test_dashboard_object_relations tests.unit.test_dashboard_layout_contract -v
```

If Node.js is available, the tests also run `node -c` over committed JS
templates.
