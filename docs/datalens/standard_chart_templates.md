# Standard chart templates

`templates/datalens/standard_chart_templates.json` is the active template
registry. `generate_editor_bundle(..., family=...)` resolves the requested
family through the approved taxonomy and then loads the matching MCP-native
template before falling back to older gallery examples.

## Source Basis

The templates distill project-authored dashboard implementation patterns into
reusable archetypes:

- KPI cards: title/hint consistency, comparison value, and no-data as a state.
- Time series: grain-aware labels, denser y-grid, top legend, direct endpoint
  labels, and safe tooltip/hint placement.
- Category comparison: sorted bars as the default replacement for removed
  lollipop, dumbbell, and plain stacked-bar requests.
- Distribution and relationship: numeric-field validation and visible axes.
- Part-to-whole: pie and donut are one decision family with small category sets.
- Flow: explicit source-target-value rows only.
- Table, selector, and Markdown: separate DataLens routes, not Advanced fallbacks.

## Template Shape

Each registered template has:

- `meta.json`
- `params.json`
- route-specific JS tabs such as `sources.js`, `prepare.js`, `controls.js`, or
  `config.js`
- `schema.json`
- `example_input.json`
- `README.md`

`params.json` is converted to the `params.js` tab by the MCP loader. This keeps
the template input small and deterministic while preserving DataLens Editor tab
contracts.

Production bundle generation never copies the archetype's example SQL into
`sources.js`. Callers must supply `dataset_alias` plus the renderer output
aliases listed in the generated `source_contract`. Missing or mismatched source
fields produce an empty `sources.js`, `generation_status=blocked_missing_source`,
and actionable blocking issues. Example rows are available only through the
explicit `golden_fixture` source mode used by the static regression gallery.

## Active Archetypes

| Template | Families |
|---|---|
| `templates/datalens/advanced_editor/kpi_card` | `kpi_value_only`, `kpi_value_delta`, `kpi_value_sparkline`, `kpi_value_delta_sparkline` |
| `templates/datalens/advanced_editor/time_series` | `line_chart`, `multiline_chart`, `area_completion`, `vertical_bar_time_bucket`, `combo_time_series_combo`, `funnel_snapshot` |
| `templates/datalens/advanced_editor/category_comparison` | `horizontal_bar`, `grouped_bar`, `stacked_100`, `bullet_assignees`, `heatmap`, `waterfall` |
| `templates/datalens/advanced_editor/distribution_relationship` | `histogram`, `box_plot`, `scatter`, `bubble` |
| `templates/datalens/advanced_editor/part_whole_hierarchy` | `pie`, `donut`, `treemap` |
| `templates/datalens/advanced_editor/flow_sankey` | `sankey_status_flow` |
| `templates/datalens/advanced_editor/grouped_sticky_table_exception` | `grouped_sticky_table_exception` |
| `templates/datalens/editor_table/table_node` | `table_node` |
| `templates/datalens/editor_js_control/selector` | selector families |
| `templates/datalens/editor_markdown/markdown_block` | Markdown families |

## Guardrails

- Removed chart families are not registered.
- Templates use `Editor.wrapFn` plus `Editor.generateHtml` for Advanced renderers.
- Visual decisions follow `style guide -> template params -> generated chart code`;
  prompts do not choose ad hoc colors.
- Template JS uses comments to mark data binding, prepare, render/layout, theme,
  and safe-render sections.
- Templates contain no source workbook IDs, dataset IDs, local paths, or source
  env references.
- Display titles remain business-readable. Generated `entry.name` values are
  separate ASCII technical names; Cyrillic is deterministically transliterated
  and the caller's widget key participates in non-ASCII name generation.
