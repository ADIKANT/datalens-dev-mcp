# Мониторинг состояния

**Русский** · [English](README_en.md)

[← Cookbook](../../README.md) · [Web](https://adikant.github.io/datalens-dev-mcp/cases/status-monitoring/?lang=ru)

Период, категория, KPI, heatmap и таблица состояний в одном связанном примере.

## Карта параметров

| Параметр | Владелец | Читатели | Тип | Default | Назначение |
| --- | --- | --- | --- | --- | --- |
| `dateFrom` | `filters` | `kpi, heatmap, status_table` | `ISO date` | `["2026-01-01"]` | Начало периода мониторинга |
| `dateTo` | `filters` | `kpi, heatmap, status_table` | `ISO date` | `["2026-01-30"]` | Конец периода мониторинга |
| `category` | `filters` | `kpi, heatmap, status_table` | `string[]` | `[]` | Категория; пусто означает все |

## Порядок копирования

1. `filters` — `editor_js_control`
2. `kpi` — `editor_advanced`
3. `heatmap` — `editor_advanced`
4. `status_table` — `editor_table`

Dataset — основной режим; ClickHouse — отдельная альтернатива с предварительной агрегацией.
