# Status monitoring

[Русский](README.md) · **English**

[← Cookbook](../../README_en.md) · [Web](https://adikant.github.io/datalens-dev-mcp/cases/status-monitoring/?lang=en)

A period, category, KPI, heatmap, and status table in one linked example.

## Parameter map

| Param | Owner | Readers | Type | Default | Purpose |
| --- | --- | --- | --- | --- | --- |
| `dateFrom` | `filters` | `kpi, heatmap, status_table` | `ISO date` | `["2026-01-01"]` | Monitoring period start |
| `dateTo` | `filters` | `kpi, heatmap, status_table` | `ISO date` | `["2026-01-30"]` | Monitoring period end |
| `category` | `filters` | `kpi, heatmap, status_table` | `string[]` | `[]` | Category; empty means all |

## Copy order

1. `filters` — `editor_js_control`
2. `kpi` — `editor_advanced`
3. `heatmap` — `editor_advanced`
4. `status_table` — `editor_table`

Dataset is the default mode; ClickHouse is an explicit pre-aggregated alternative.
