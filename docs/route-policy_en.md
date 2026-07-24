# Chart technology selection

[Русский](route-policy.md) · **English** · [Tools](tools_en.md) · [Sources](sources_en.md)

Official model: [Wizard, QL, and Editor](https://yandex.cloud/ru/docs/datalens/concepts/chart/). The server's versioned rules are in `config/route_selection_policy_v5.json`.

## Selection rules

1. An update preserves technology and `visualization_id` from current saved state.
2. A create honors a direct user request for Wizard, Editor, or QL.
3. Editor is used for requested JavaScript or a capability unavailable in a suitable Wizard chart.
4. Standard visualizations use Wizard.
5. An API failure does not trigger an automatic technology change.

The decision contains route, `visualization_id`, and an explanation.

## Standard Wizard visualizations

| Chart | `visualization_id` |
| --- | --- |
| Metric and metric with delta | `metric` |
| Flat table | `flatTable` |
| Pivot table | `pivotTable` |
| Line | `line` |
| Area | `area`, `area100p` |
| Vertical columns | `column`, `column100p` |
| Horizontal bars | `bar`, `bar100p` |
| Combined chart | `combined-chart` |
| Pie and donut | `pie`, `donut` |
| Scatter and bubble | `scatter` |
| Treemap | `treemap` |
| Map | `geolayer` |

A bubble chart requires a size field and a map requires verified geo data. `wizard_map_native` is normalized to `wizard_native` with `visualization_id=geolayer`.

## Editor

- `editor_advanced` — general JavaScript chart;
- `editor_table` — specialized JavaScript table;
- `editor_markdown` — Markdown object;
- `editor_js_control` — JavaScript control.

Before save, an Editor object passes `dl_validate_editor_runtime_contract` against official [tabs](https://yandex.cloud/ru/docs/datalens/charts/editor/tabs) and [methods](https://yandex.cloud/ru/docs/datalens/charts/editor/methods).

An explicit project `authoring_profile: {"id": "standard_editor_v1"}` is a
JavaScript contract for every supported family. It does not change the global
Wizard-first default: the profile selects only a registered Editor asset,
returns SHA-256 identities for the template set, selected assets, style
contract, and compiled tabs, and refuses approximate fallback. Generation is
blocked for an unregistered family or a native map.

A project-local profile is declared with `id`, `descriptor_path`, and
`descriptor_sha256`. Its descriptor registers exact Editor-family assets; the
descriptor and every dependency must stay inside the project root, and the
complete template-set fingerprint is checked before generation. This profile
does not expand supported technologies or permit fallback.

## QL

`ql_explicit` is selected only after a direct user request for QL. Creation and updates use an explicit payload or current saved QL object. The server does not generate QL from a general request or select it after a Wizard or Editor failure.

## Create and update

For a new Wizard chart, the server prefers a current saved seed with the same `visualization_id`, strips source-object identities, and binds target dataset fields. A packaged canonical template is used when no seed exists.

An update takes technology, visualization, unknown fields, and revision from current readback. Publishing is governed by [Safe Apply](safe-apply_en.md), independently of chart technology.
