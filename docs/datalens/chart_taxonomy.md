# DataLens chart taxonomy

This is the MCP-native standard visualization set maintained as a
project-authored runtime contract. Runtime routing and
template selection must use these families only.

Template registration lives in
`templates/datalens/standard_chart_templates.json`; removed chart families are
not registered there.

Runtime routing also reads `config/datalens_chart_param_matrix.json`. The matrix
defines route, data shape, required parameters, visual rules, ask-user triggers,
and fallback family for every supported family. A family is not generation-ready
unless both the taxonomy and matrix cover it.

## Supported standard charts

| Family | Route | Use |
|---|---|---|
| `kpi_value_only` | `wizard_native` / `metric` | Single current value with consistent title and hint. |
| `kpi_value_delta` | `wizard_native` / `metric` | Current value and explicit comparator delta. |
| `kpi_value_sparkline` | `editor_advanced` | KPI value with compact trend context. |
| `kpi_value_delta_sparkline` | `editor_advanced` | KPI value with trend and explicit comparator delta. |
| `line_chart` | `wizard_native` / `line` | Continuous trend with grain-aware x-axis, y-axis labels, point labels for peaks/drops, and tooltip. |
| `multiline_chart` | `wizard_native` / `line` | Comparable time series with top legend and shared time grain. |
| `area_completion` | `wizard_native` / `area` | Completion or accumulation trend when area encoding has meaning. |
| `vertical_bar_time_bucket` | `wizard_native` / `column` | Discrete time bucket comparison with zero baseline and value labels. |
| `combo_time_series_combo` | `wizard_native` / `combined-chart` | Bar plus line when both metrics belong in one time frame. |
| `horizontal_bar` | `wizard_native` / `bar` | Sorted category comparison, ranking, or top-N. |
| `grouped_bar` | `wizard_native` / `bar` | Side-by-side comparison across category and series. |
| `stacked_100` | `wizard_native` / `column100p` | Composition comparison where each bar is a common whole. |
| `bullet_assignees` | `editor_advanced` | Actual versus target with explicit target and scroll/readability rules. |
| `heatmap` | `editor_advanced` | Matrix intensity with meaningful color scale and sparse-cell policy. |
| `waterfall` | `editor_advanced` | Contribution bridge with axis, gridlines, and labels. |
| `funnel_snapshot` | `editor_advanced` | Ordered stage leakage for one funnel frame. |
| `sankey_status_flow` | `editor_advanced` | Flow volumes only when stages, direction, and conservation are explicit. |
| `histogram` | `editor_advanced` | Numeric distribution bins. |
| `box_plot` | `editor_advanced` | Distribution summary by category with quartile/outlier rules. |
| `scatter` | `wizard_native` / `scatter` | Relationship between two numeric measures with labeled axes. |
| `bubble` | `wizard_native` / `scatter` | Scatter plus mandatory size role. |
| `pie` / `donut` | `wizard_native` / `pie`, `donut` | Small part-to-whole sets; use one decision family. |
| `treemap` | `wizard_native` / `treemap` | Hierarchical part-to-whole where area meaning is obvious. |
| `table_node` | `wizard_native` / `flatTable` | Default exact-value table, registry, and source matrix route. |
| `pivot_table_node` | `wizard_native` / `pivotTable` | Standard pivot with explicit row, column, and measure roles. |
| `grouped_sticky_table_exception` | reference only | Blocked: HTML table markup fails the current Advanced Editor runtime contract; use native `table_node` with `head.sub`. |
| `table_pivot_advanced_exception` | reference only | Discoverable migration reference only; creation and generation are blocked in favor of native `table_pivot_js` with nested `head.sub`. |
| `resource_schedule_exception` | `editor_advanced` | Explicit-only bounded resource-by-time schedule when interval conflicts are the analytical task; never a generic timeline fallback. |
| Markdown families | `editor_markdown` | Section headers, owner/source notes, methodology, contacts, and links. |
| Selector families | `editor_js_control` | Static, dynamic, search, multi-select, and date controls. |

Native maps are represented as `native_map_geo_widget` in the parameter matrix
and route to `wizard_native/geolayer`. `wizard_map_native` remains an input
accepted input normalized to the canonical route.

## Supported but needing template improvement

These families remain reachable, but templates must follow the shared chart
contract: every chart has a hint; x-axis grain supports day/week/month where
time is present; y-axis ticks are readable; labels are shown on bars, key points,
peaks, or drops; legends sit above when multiple series exist; tooltips use the
standard shell; category colors do not reuse semantic alert colors.

| Family | Required improvement |
|---|---|
| `kpi_value_delta` | Require an explicit comparator field or declared baseline; never infer previous period. |
| `kpi_value_delta_sparkline` | Keep number sizing responsive and include comparator delta only when declared. |
| `line_chart`, `multiline_chart`, `area_completion` | Use grain-aware axes, peak/drop labels, and standard tooltip. |
| `combo_time_series_combo`, `vertical_bar_time_bucket`, `grouped_bar`, `stacked_100` | Keep bar width consistent and label both bars and line points where applicable. |
| `horizontal_bar`, `bullet_assignees` | Use the standard ranking style, readable scroll behavior, and direct labels. |
| `heatmap`, `waterfall`, `funnel_snapshot`, `sankey_status_flow` | Tighten grid, color, axis, label, and scenario gates. |
| `histogram`, `box_plot`, `scatter`, `bubble` | Require numeric-field validation and clear axis/legend semantics. |
| `pie`, `donut`, `treemap` | Keep category count small and avoid decorative part-to-whole use. |
| `table_node` | Keep default table simple; custom HTML table requires explicit exception evidence. |

## Manual review only

`slope_chart` and `bump_chart` are not normal routing or gallery options. If a
user explicitly asks for one, route the request through manual review and start
from `line_chart` or `horizontal_bar` unless the source data proves that the
specialized pattern is necessary.

QL charts are never default recommendations. A direct user request may use
`ql_explicit` through generic read/create/update lifecycle tools with explicit
payload or fresh saved seed; automatic selection and delete remain closed.
