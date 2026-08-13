# Период, сравнение и шаг по времени

**Русский** · [English](README_en.md)

[← Cookbook](../../README.md) · [Web](https://adikant.github.io/datalens-dev-mcp/cases/period-comparison-time-step/?lang=ru)

Диапазон дат, способ сравнения, auto/day/week/month, KPI и линия current versus comparison.

## Карта параметров

| Параметр | Владелец | Читатели | Тип | Default | Назначение |
| --- | --- | --- | --- | --- | --- |
| `dateFrom` | `period_selector` | `comparison_selector, time_step_selector, kpi, trend` | `ISO date` | `["2026-01-01"]` | Начало выбранного периода |
| `dateTo` | `period_selector` | `comparison_selector, time_step_selector, kpi, trend` | `ISO date` | `["2026-01-30"]` | Конец выбранного периода |
| `comparisonMethod` | `comparison_selector` | `kpi, trend` | `previous_period | previous_year` | `["previous_period"]` | Способ построения периода сравнения |
| `timeStep` | `time_step_selector` | `trend` | `auto | day | week | month` | `["auto"]` | Шаг агрегации; auto выбирает day до 14 дней, week для 15–60, month для более длинного периода |

## Порядок копирования

1. `period_selector` — `editor_js_control`
2. `comparison_selector` — `editor_js_control`
3. `time_step_selector` — `editor_js_control`
4. `kpi` — `editor_advanced`
5. `trend` — `editor_advanced`

Dataset — основной режим; ClickHouse — отдельная альтернатива с предварительной агрегацией.
