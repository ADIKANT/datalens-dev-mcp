# Показатель: значение и тренд

**Русский** · [English](README_en.md)

[← Cookbook](../../README.md) · [Web](https://adikant.github.io/datalens-dev-mcp/recipes/kpi-value-sparkline/?lang=ru)

![Показатель: значение и тренд](preview.svg)

Показатель с компактным мини-графиком.

## Когда использовать

Текущий итог, для которого важна форма недавней динамики.

## Особенности поведения

Sparkline пропускает null без выдумывания значений.

## Контракт Sources

| Alias | Назначение | Тип / формат | Поведение null | Пример |
| --- | --- | --- | --- | --- |
| `current_value` | Текущее значение показателя | `number` / finite number | Показывается состояние без данных | `128` |
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
