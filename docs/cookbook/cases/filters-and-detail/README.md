# Фильтры и детализация

**Русский** · [English](README_en.md)

[← Cookbook](../../README.md) · [Web](https://adikant.github.io/datalens-dev-mcp/cases/filters-and-detail/?lang=ru)

Период, динамический searchable selector, multiselect статусов, сводный график и связанная детальная таблица.

## Карта параметров

| Параметр | Владелец | Читатели | Тип | Default | Назначение |
| --- | --- | --- | --- | --- | --- |
| `dateFrom` | `filters` | `summary, detail` | `ISO date` | `["2026-01-01"]` | Начало периода |
| `dateTo` | `filters` | `summary, detail` | `ISO date` | `["2026-01-30"]` | Конец периода |
| `category` | `filters` | `summary, detail` | `string[]` | `[]` | Поисковый динамический фильтр категории |
| `status` | `filters` | `summary, detail` | `string[]` | `[]` | Множественный фильтр состояний; пусто означает все |

## Порядок копирования

1. `filters` — `editor_js_control`
2. `summary` — `editor_advanced`
3. `detail` — `editor_table`

Dataset — основной режим; ClickHouse — отдельная альтернатива с предварительной агрегацией.
