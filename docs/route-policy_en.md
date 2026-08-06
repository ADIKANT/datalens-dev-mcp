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

Create and full-redesign calls without an explicit profile use
`standard_dashboard_v1`; `strict_dashboard`, `standard_dashboard`, and
`registered_dashboard` are aliases. The profile fixes the canonical route
first: standard KPI, table, and chart creation stays on Wizard. It applies
For a selected Editor object, the same `standard_dashboard_v1` profile applies
the current protected renderer only to an explicitly requested Editor object,
a verified capability gap, or preserved Editor technology during an update.

There is one executable built-in contract. Historical profile names are input
aliases that immediately normalize to `standard_dashboard_v1`; they cannot
select historical assets or rules. A saved Editor object stays Editor, but its
bundle is regenerated with the current contract. The profile returns SHA-256
identities for its template set, selected assets, render
contract, and compiled tabs and refuses approximate fallback. The planned route
is part of final payload attestation, so a project compiler cannot turn a
planned Wizard dashboard into Editor objects.

A project-local profile is declared with `id`, `descriptor_path`, and
`descriptor_sha256`. Its descriptor registers exact Editor-family assets; the
descriptor and every dependency must stay inside the project root, and the
complete template-set fingerprint is checked before generation. This profile
does not expand supported technologies or permit fallback, and a descriptor
cannot override a reserved built-in profile name or alias.

## QL

`ql_explicit` is selected only after a direct user request for QL. Creation and updates use an explicit payload or current saved QL object. The server does not generate QL from a general request or select it after a Wizard or Editor failure.

## Create and update

For a new Wizard chart, the server prefers a current saved seed with the same `visualization_id`, strips source-object identities, and binds target dataset fields. A packaged canonical template is used when no seed exists.

An update takes technology, visualization, unknown fields, and revision from current readback. Publishing is governed by [Safe Apply](safe-apply_en.md), independently of chart technology.

## Composition and title contract

Renderer Visual Spec v5 assigns title ownership through `title_mode`: an Editor
chart uses `embedded_title`, a KPI uses `content_label`, content named only by
its dashboard tab uses `tab_only`, Wizard/native tables use `native_title`, and
an inner tab switcher uses `tab_strip`. Native and runtime title ownership may
not coexist. The accepted `display_title` is exact and cannot be replaced with
a technical object name.

`dashboard_composition.version=2` binds semantic rows, 36-column geometry,
selectors, and mount → tab → widget relationships. Any route, title, selector,
runtime, or layout change after `dl_validate_project` invalidates final payload
attestation.
