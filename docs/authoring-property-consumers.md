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
