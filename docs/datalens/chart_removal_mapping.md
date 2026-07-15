# Chart removal mapping

| Removed chart | Reason | Approved alternative | Files changed | Notes |
|---|---|---|---|---|
| `g02_kpi_status_blocked` | Standalone KPI status cards are not required. | `kpi_value_sparkline` | `src/datalens_dev_mcp/pipeline/chart_taxonomy.py`, `src/datalens_dev_mcp/editor/bundle.py` | Status is state/formatting inside KPI cards, not a family. |
| `g05_kpi_no_data` | No-data is a state, not a chart type. | `kpi_value_sparkline` | `src/datalens_dev_mcp/pipeline/chart_taxonomy.py` | Existing KPI templates must handle empty data. |
| `g06_kpi_strip_composite` | Composite KPI strips should not be selected automatically. | `kpi_value_delta` | `src/datalens_dev_mcp/pipeline/chart_taxonomy.py` | Use separate KPI widgets if explicitly designed. |
| `g13_slope_type_open` | Current implementation is not useful enough for normal routing. | `line_chart` | `src/datalens_dev_mcp/pipeline/chart_taxonomy.py` | Manual review only. |
| `g14_bump_priority_rank` | Rank-over-time needs strict evidence and should not be a default option. | `horizontal_bar` | `src/datalens_dev_mcp/pipeline/chart_taxonomy.py`, `examples/gallery/timeseries-combo/prepare.js`, `examples/gallery/timeseries-combo/sources.js` | Removed from normal gallery. |
| `g15_streamgraph_status_category` | Low decision value versus simpler trend/composition charts. | `area_completion` | `src/datalens_dev_mcp/pipeline/chart_taxonomy.py` | Not a normal routing option. |
| `g16_sparkline_created` | Duplicates area chart or KPI sparkline use. | `area_completion` | `src/datalens_dev_mcp/pipeline/chart_taxonomy.py` | Standalone sparkline is removed. |
| `g18_timeline_created` | Not common enough for standard operational dashboards. | `line_chart` | `src/datalens_dev_mcp/pipeline/chart_taxonomy.py` | Use line or table depending on event granularity. |
| `g19_small_multiple_priority` | Adds layout complexity without enough value. | `grouped_bar` | `src/datalens_dev_mcp/pipeline/chart_taxonomy.py` | Selector-filtered chart can replace it. |
| `g23_stacked_bar_status_type` | Plain stacked bars are harder to compare. | `stacked_100` | `src/datalens_dev_mcp/pipeline/chart_taxonomy.py` | Use grouped bar when exact segment magnitude matters. |
| `g25_lollipop_epics` | Removed from standard plugin space. | `horizontal_bar` | `src/datalens_dev_mcp/pipeline/chart_taxonomy.py` | Sorted bars answer the same ranking question. |
| `g27_dumbbell_type_created_completed` | Removed from standard plugin space. | `grouped_bar` | `src/datalens_dev_mcp/pipeline/chart_taxonomy.py` | Grouped bars are clearer for paired category values. |
| `g41_density_age` | Density plots are not standard for this dashboard audience. | `histogram` | `src/datalens_dev_mcp/pipeline/chart_taxonomy.py` | Use `box_plot` when category comparison of distribution is primary. |
| `g43_jitter_priority_age` | Jitter plots are too specialized for normal routing. | `scatter` | `src/datalens_dev_mcp/pipeline/chart_taxonomy.py` | Use scatter only with two numeric measures. |
| `g44_beeswarm_priority_age` | Beeswarm plots are too specialized for normal routing. | `box_plot` | `src/datalens_dev_mcp/pipeline/chart_taxonomy.py` | Use box plot or histogram. |
| `g60_table_standard` | Table aliases collapse into the single table route. | `table_node` | `src/datalens_dev_mcp/pipeline/chart_taxonomy.py`, `examples/gallery/editor-table-registry/config.js`, `examples/gallery/editor-table-registry/params.js`, `examples/gallery/editor-table-registry/prepare.js` | Default table remains available. |
| `g61_table_custom_bars` | Bar-in-table is formatting, not a chart family. | `table_node` | `src/datalens_dev_mcp/pipeline/chart_taxonomy.py`, `examples/gallery/editor-table-registry/config.js`, `examples/gallery/editor-table-registry/prepare.js` | Custom table requires explicit exception. |
| `g62_registry_table` | Registry table is covered by `table_node`. | `table_node` | `src/datalens_dev_mcp/pipeline/chart_taxonomy.py` | Use config/title/sort on the table route. |
| `g63_summary_rows_table` | Summary rows are table configuration. | `table_node` | `src/datalens_dev_mcp/pipeline/chart_taxonomy.py` | Not a separate family. |
| `g64_status_heat_table` | Status heat tables are table configuration. | `table_node` | `src/datalens_dev_mcp/pipeline/chart_taxonomy.py` | Use heatmap only for real matrix intensity. |
| `g65_table_sparkline` | Table sparklines are not generated standard families. | `table_node` | `src/datalens_dev_mcp/pipeline/chart_taxonomy.py`, `examples/gallery/editor-table-registry/config.js`, `examples/gallery/editor-table-registry/prepare.js` | Trend belongs in chart/KPI unless a rare table exception is approved. |
