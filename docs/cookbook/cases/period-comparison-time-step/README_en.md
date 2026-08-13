# Period, comparison, and time step

[Русский](README.md) · **English**

[← Cookbook](../../README_en.md) · [Web](https://adikant.github.io/datalens-dev-mcp/cases/period-comparison-time-step/?lang=en)

Date range, comparison method, auto/day/week/month, KPI, and current-versus-comparison line.

## Parameter map

| Param | Owner | Readers | Type | Default | Purpose |
| --- | --- | --- | --- | --- | --- |
| `dateFrom` | `period_selector` | `comparison_selector, time_step_selector, kpi, trend` | `ISO date` | `["2026-01-01"]` | Selected period start |
| `dateTo` | `period_selector` | `comparison_selector, time_step_selector, kpi, trend` | `ISO date` | `["2026-01-30"]` | Selected period end |
| `comparisonMethod` | `comparison_selector` | `kpi, trend` | `previous_period | previous_year` | `["previous_period"]` | How the comparison period is derived |
| `timeStep` | `time_step_selector` | `trend` | `auto | day | week | month` | `["auto"]` | Aggregation step; auto selects day up to 14 days, week for 15–60, and month for longer ranges |

## Copy order

1. `period_selector` — `editor_js_control`
2. `comparison_selector` — `editor_js_control`
3. `time_step_selector` — `editor_js_control`
4. `kpi` — `editor_advanced`
5. `trend` — `editor_advanced`

Dataset is the default mode; ClickHouse is an explicit pre-aggregated alternative.
