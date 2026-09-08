# Authoring property consumers

Recipe output is accepted only when the named consumer applies the property. A value merely present in `visual_contract` is not runtime proof.

| Property | Applying consumer | Observable check |
| --- | --- | --- |
| Object name | SDK create/update metadata | Saved object metadata contains the requested name. |
| Visible title and owner | Dashboard widget, Wizard title, or Editor renderer | The title appears exactly once at the selected owner. |
| Hint | Wizard native hint or Editor `tooltip.renderer` hint target | Hover opens the requested explanatory content. |
| Tooltip | Wizard datum tooltip or Editor `tooltip.renderer` | Hover contains the bound metric, unit, periods, value and comparison limitations. |
| Labels, precision, unit and sign | Wizard role/format settings or Editor formatter | Rendered labels resolve concrete formatting; `from_field` is not left unresolved. |
| Gridlines, ticks and zero baseline | Wizard chart settings | Saved settings and rendered axes match the selected family. |
| Legend | Wizard series settings or Editor renderer | Only the configured, visible semantic items appear in configured order. |
| Comparison | Dataset fields/source prepare plus family renderer | Method, current/previous boundaries, cutoff, missing values and delta kind remain distinct. |
| Table structure | Wizard table settings or Editor table renderer | Column order/widths, sticky headers/edges, totals and internal scrolling are rendered. |
| Theme and geometry | DataLens theme tokens, dashboard widget geometry and renderer viewport | Auto inherits DataLens CSS variables; saved widget size is preserved on narrow updates. |
| Selector semantics | Editor control params and dashboard consumer bindings | Default, empty/clear, select-all and every declared consumer use the same parameter. |

The three reference-complete families are `kpi_sparkline`, `comparison_matrix` (dynamic multi-level version matrix), and `weekly_totals_table` (ISO-week totals). `cross_tab_totals` remains the native Wizard pivot route when its properties are sufficient.

Static renderer tests prove property application in the packaged function. Provider save/readback, Dataset/source execution and Browser rendering are separate evidence levels.

## Dataset weekly source semantics

The `weekly_totals_table` Dataset shortcut reads aggregation from the selected metric's Dataset field readback and/or `metric.aggregation`. It sums group/date rows into ISO weeks only when the known aggregations are `sum` or `count`; conflicting or unknown aggregation (including `none`) is rejected. `metric.additive: true` alone does not establish aggregation, and cannot override an average, ratio or distinct count. A Dataset query must represent the intended group/date partitions: additive totals do not deduplicate overlapping source populations.

For averages, ratios and distinct counts, supply an explicit `source` transform or `prepared_data` with `rows[].total`, `total_values` and `grand_total` computed at the source's proper grain. An explicit prepared result takes precedence over the Dataset shortcut even when `dataset_id` is retained as context. For example, 8/10 and 18/20 require a combined ratio of 26/30; neither adding percentages nor averaging those ratios gives the correct total. Supplied totals remain unchanged.

Explicit null, absent metric values and empty/whitespace strings stay unknown. Any unknown component makes the corresponding weekly cell and row/column/grand total null, rendered as a dash. Actual numeric zero remains zero. Missing group/week combinations default to null; `rows[].value_states` distinguishes `missing`, `unknown` and `value`. For count measures only, `metric.missing_combinations: "zero"` declares absent combinations to be zero, while explicit unknowns still propagate. The default policy is `"unknown"`. Weeks are drawn from the returned rows, not an invented calendar range.

Dataset parameters accept a scalar or singleton array, normalized to one string value in `{id, value}`. Numeric zero and boolean false become `"0"` and `"false"`. Null, undefined, empty string and empty/cleared arrays omit the parameter; omitted parameters use the Dataset's own behavior. Multiple nonempty values are rejected because this binding does not support multivalue Dataset parameters. Selector filters keep their separate `where` contract and clear policy.
