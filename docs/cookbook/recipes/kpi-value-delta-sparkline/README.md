# Показатель: дельта и тренд

**Русский** · [English](README_en.md)

[← Cookbook](../../README.md) · [Web](https://adikant.github.io/datalens-dev-mcp/recipes/kpi-value-delta-sparkline/?lang=ru)

![Показатель: дельта и тренд](preview.svg)

KPI со значением, явным сравнением и мини-графиком.

## Когда использовать

Главный показатель, где нужны уровень, изменение и динамика.

## Особенности поведения

Tooltip показывает значения временных точек и контекст сравнения.

## Контракт Sources

| Alias | Назначение | Тип / формат | Поведение null | Пример |
| --- | --- | --- | --- | --- |
| `current_value` | Текущее значение показателя | `number` / finite number | Показывается состояние без данных | `128` |
| `comparator_value` | Явное значение для сравнения | `number` / finite number | Дельта не рассчитывается | `120` |
| `sparkline` | Последовательность значений мини-графика | `string` / JSON number array | Мини-график скрывается | `"[82,91,97,104,128]"` |

## Что менять

1. Замените только Meta и Sources, сохранив aliases.
2. Для необязательных подписей, палитры, единиц и форматов используйте блок CUSTOMIZE.

## Файлы

- [`meta.json`](code/ru/meta.json)
- [`params.js`](code/ru/params.js)
- [`sources.js`](code/ru/sources.js)
- [`controls.js`](code/ru/controls.js)
- [`prepare.js`](code/ru/prepare.js)
- [`schema.json`](code/ru/schema.json)
- [`example_input.json`](code/ru/example_input.json)
