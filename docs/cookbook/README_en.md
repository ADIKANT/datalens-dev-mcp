# JavaScript Visualization Cookbook

[Русский](README.md) · **English**

The cookbook starts with shared Tips, then provides 34 standalone recipes and three linked cases.

- [Tips](index.html?lang=en)
- [Visualizations](visualizations/index.html?lang=en)
- [Cases](cases/index.html?lang=en)

## Visualizations

| Recipe | Family | Route | SVG |
| --- | --- | --- | --- |
| [KPI: single value](recipes/kpi-value-only/README_en.md) | `kpi_value_only` | `editor_advanced` | [SVG](recipes/kpi-value-only/preview_en.svg) |
| [KPI: value and delta](recipes/kpi-value-delta/README_en.md) | `kpi_value_delta` | `editor_advanced` | [SVG](recipes/kpi-value-delta/preview_en.svg) |
| [KPI: value and trend](recipes/kpi-value-sparkline/README_en.md) | `kpi_value_sparkline` | `editor_advanced` | [SVG](recipes/kpi-value-sparkline/preview_en.svg) |
| [KPI: delta and trend](recipes/kpi-value-delta-sparkline/README_en.md) | `kpi_value_delta_sparkline` | `editor_advanced` | [SVG](recipes/kpi-value-delta-sparkline/preview_en.svg) |
| [Line trend](recipes/line-chart/README_en.md) | `line_chart` | `editor_advanced` | [SVG](recipes/line-chart/preview_en.svg) |
| [Multiple time series](recipes/multiline-chart/README_en.md) | `multiline_chart` | `editor_advanced` | [SVG](recipes/multiline-chart/preview_en.svg) |
| [Area chart](recipes/area-chart/README_en.md) | `area_completion` | `editor_advanced` | [SVG](recipes/area-chart/preview_en.svg) |
| [Cumulative line](recipes/cumulative-line/README_en.md) | `line_chart` | `editor_advanced` | [SVG](recipes/cumulative-line/preview_en.svg) |
| [Bars by time interval](recipes/vertical-bar-time-bucket/README_en.md) | `vertical_bar_time_bucket` | `editor_advanced` | [SVG](recipes/vertical-bar-time-bucket/preview_en.svg) |
| [Combined time series](recipes/combo-time-series/README_en.md) | `combo_time_series_combo` | `editor_advanced` | [SVG](recipes/combo-time-series/preview_en.svg) |
| [Horizontal ranking](recipes/horizontal-bar/README_en.md) | `horizontal_bar` | `editor_advanced` | [SVG](recipes/horizontal-bar/preview_en.svg) |
| [Grouped horizontal bars](recipes/grouped-bar/README_en.md) | `grouped_bar` | `editor_advanced` | [SVG](recipes/grouped-bar/preview_en.svg) |
| [100% stacked](recipes/stacked-100/README_en.md) | `stacked_100` | `editor_advanced` | [SVG](recipes/stacked-100/preview_en.svg) |
| [Bullet: actual and target](recipes/bullet-actual-target/README_en.md) | `bullet_assignees` | `editor_advanced` | [SVG](recipes/bullet-actual-target/preview_en.svg) |
| [Matrix heatmap](recipes/matrix-heatmap/README_en.md) | `heatmap` | `editor_advanced` | [SVG](recipes/matrix-heatmap/preview_en.svg) |
| [Waterfall](recipes/waterfall/README_en.md) | `waterfall` | `editor_advanced` | [SVG](recipes/waterfall/preview_en.svg) |
| [Funnel](recipes/funnel/README_en.md) | `funnel_snapshot` | `editor_advanced` | [SVG](recipes/funnel/preview_en.svg) |
| [Sankey](recipes/sankey/README_en.md) | `sankey_status_flow` | `editor_advanced` | [SVG](recipes/sankey/preview_en.svg) |
| [Histogram](recipes/histogram/README_en.md) | `histogram` | `editor_advanced` | [SVG](recipes/histogram/preview_en.svg) |
| [Box plot](recipes/box-plot/README_en.md) | `box_plot` | `editor_advanced` | [SVG](recipes/box-plot/preview_en.svg) |
| [Scatter plot](recipes/scatter/README_en.md) | `scatter` | `editor_advanced` | [SVG](recipes/scatter/preview_en.svg) |
| [Bubble chart](recipes/bubble/README_en.md) | `bubble` | `editor_advanced` | [SVG](recipes/bubble/preview_en.svg) |
| [Pie chart](recipes/pie/README_en.md) | `pie` | `editor_advanced` | [SVG](recipes/pie/preview_en.svg) |
| [Donut chart](recipes/donut/README_en.md) | `donut` | `editor_advanced` | [SVG](recipes/donut/preview_en.svg) |
| [Treemap](recipes/treemap/README_en.md) | `treemap` | `editor_advanced` | [SVG](recipes/treemap/preview_en.svg) |
| [Compact table](recipes/editor-table/README_en.md) | `table_node` | `editor_table` | [SVG](recipes/editor-table/preview_en.svg) |
| [Wide detail table](recipes/detail-table/README_en.md) | `table_node` | `editor_table` | [SVG](recipes/detail-table/preview_en.svg) |
| [Status table](recipes/status-table/README_en.md) | `table_node` | `editor_table` | [SVG](recipes/status-table/preview_en.svg) |
| [Grouped summary table](recipes/grouped-summary-table/README_en.md) | `table_node` | `editor_table` | [SVG](recipes/grouped-summary-table/preview_en.svg) |
| [Search selector](recipes/search-selector/README_en.md) | `search_selector` | `editor_js_control` | [SVG](recipes/search-selector/preview_en.svg) |
| [Date range selector](recipes/date-range-selector/README_en.md) | `date_range_selector` | `editor_js_control` | [SVG](recipes/date-range-selector/preview_en.svg) |
| [Static selector](recipes/static-selector/README_en.md) | `selector_family_static` | `editor_js_control` | [SVG](recipes/static-selector/preview_en.svg) |
| [Dynamic selector](recipes/dynamic-selector/README_en.md) | `selector_family_dynamic` | `editor_js_control` | [SVG](recipes/dynamic-selector/preview_en.svg) |
| [Selector group](recipes/selector-group/README_en.md) | `selector_group` | `editor_js_control` | [SVG](recipes/selector-group/preview_en.svg) |

## Cases

- [Period, comparison, and time step](cases/period-comparison-time-step/README_en.md)
- [Filters and detail](cases/filters-and-detail/README_en.md)
- [Status monitoring](cases/status-monitoring/README_en.md)

```bash
python3 scripts/build_javascript_cookbook.py --write
python3 scripts/build_javascript_cookbook.py --check
```
