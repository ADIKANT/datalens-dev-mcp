# Комбинированный временной график

**Русский** · [English](README_en.md)

[← Cookbook](../../README.md) · [Web](https://adikant.github.io/datalens-dev-mcp/recipes/combo-time-series/?lang=ru)

![Комбинированный временной график](preview.svg)

Столбцы и линия в общей системе координат.

## Когда использовать

Совместное чтение объёма и связанного темпа или уровня.

## Особенности поведения

series_type явно задаёт bar или line для каждой metric.

## Контракт Sources

| Alias | Назначение | Тип / формат | Поведение null | Пример |
| --- | --- | --- | --- | --- |
| `bucket` | Начало отображаемого временного интервала после группировки — например дня, недели или месяца. Значения должны сортироваться по времени. | `string` / ISO date or interval key | Строка отбрасывается | `"2026-01-01"` |
| `metric` | Имя серии или показателя | `string` / label | Используется заголовок чарта | `"Объём"` |
| `series_type` | Тип отметки в комбинированном графике | `string` / line | bar | Первый ряд — bar, остальные — line | `"bar"` |
| `value` | Числовое значение отметки | `number` / finite number | Разрыв линии или пропуск отметки | `42` |

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
