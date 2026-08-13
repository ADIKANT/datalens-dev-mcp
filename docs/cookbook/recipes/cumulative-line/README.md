# Накопительная линия

**Русский** · [English](README_en.md)

[← Cookbook](../../README.md) · [Web](https://adikant.github.io/datalens-dev-mcp/recipes/cumulative-line/?lang=ru)

![Накопительная линия](preview.svg)

Prepare сортирует интервалы и рассчитывает накопительный итог.

## Когда использовать

Поступления или выполненный объём, заданные изменением за каждый интервал.

## Особенности поведения

Линия не имеет заливки и при положительных increments не убывает.

## Контракт Sources

| Alias | Назначение | Тип / формат | Поведение null | Пример |
| --- | --- | --- | --- | --- |
| `bucket` | Начало отображаемого временного интервала после группировки — например дня, недели или месяца. Значения должны сортироваться по времени. | `string` / ISO date or interval key | Строка отбрасывается | `"2026-01-01"` |
| `increment` | Изменение за временной интервал, которое Prepare прибавляет к накопительному итогу | `number` / finite non-zero number | Строка отбрасывается; нулевые изменения допускаются только после осознанного изменения контракта | `12` |

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
