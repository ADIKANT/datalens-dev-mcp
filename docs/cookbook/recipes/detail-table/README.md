# Широкая детальная таблица

**Русский** · [English](README_en.md)

[← Cookbook](../../README.md) · [Web](https://adikant.github.io/datalens-dev-mcp/recipes/detail-table/?lang=ru)

![Широкая детальная таблица](preview.svg)

Закреплённые ключи, форматы, hints, пагинация и горизонтальная прокрутка.

## Когда использовать

Детализация после агрегированного графика.

## Особенности поведения

entity_id и entity_name закреплены слева; остальные колонки прокручиваются.

## Контракт Sources

| Alias | Назначение | Тип / формат | Поведение null | Пример |
| --- | --- | --- | --- | --- |
| `entity_id` | Стабильный идентификатор строки | `string` / stable identifier | Строка отбрасывается | `"OBJ-1042"` |
| `entity_name` | Название объекта | `string` / display text | Показывается entity_id | `"Объект 1042"` |
| `status` | Технический ключ состояния | `string` / status key | Используется нейтральное оформление | `"ready"` |
| `owner` | Ответственный владелец | `string` / display text | Показывается тире | `"Команда A"` |
| `updated_at` | Время последнего изменения | `string` / ISO-8601 datetime | Показывается «нет данных» | `"2026-01-05T12:30:00Z"` |
| `amount` | Числовая сумма для форматирования | `number` / finite number | Показывается тире | `1250.5` |

## Что менять

1. Замените только Meta и Sources, сохранив aliases.
2. Для необязательных подписей, палитры, единиц и форматов используйте блок CUSTOMIZE.

## Файлы

- [`meta.json`](code/ru/meta.json)
- [`params.js`](code/ru/params.js)
- [`sources.js`](code/ru/sources.js)
- [`prepare.js`](code/ru/prepare.js)
- [`config.js`](code/ru/config.js)
- [`schema.json`](code/ru/schema.json)
- [`example_input.json`](code/ru/example_input.json)
