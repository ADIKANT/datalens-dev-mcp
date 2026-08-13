# Filters and detail

[Русский](README.md) · **English**

[← Cookbook](../../README_en.md) · [Web](https://adikant.github.io/datalens-dev-mcp/cases/filters-and-detail/?lang=en)

Period, a dynamic searchable selector, status multiselect, summary chart, and linked detail table.

## Parameter map

| Param | Owner | Readers | Type | Default | Purpose |
| --- | --- | --- | --- | --- | --- |
| `dateFrom` | `filters` | `summary, detail` | `ISO date` | `["2026-01-01"]` | Period start |
| `dateTo` | `filters` | `summary, detail` | `ISO date` | `["2026-01-30"]` | Period end |
| `category` | `filters` | `summary, detail` | `string[]` | `[]` | Searchable dynamic category filter |
| `status` | `filters` | `summary, detail` | `string[]` | `[]` | Status multiselect; empty means all |

## Copy order

1. `filters` — `editor_js_control`
2. `summary` — `editor_advanced`
3. `detail` — `editor_table`

Dataset is the default mode; ClickHouse is an explicit pre-aggregated alternative.
