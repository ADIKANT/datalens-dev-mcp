# Группа селекторов

**Русский** · [English](README_en.md)

[← Cookbook](../../README.md) · [Web](https://adikant.github.io/datalens-dev-mcp/recipes/selector-group/?lang=ru)

![Группа селекторов](preview.svg)

Период, статический фильтр и динамический справочник.

## Когда использовать

Единая панель связанных параметров.

## Особенности поведения

Контролы занимают две строки и обновляются немедленно.

## Контракт Sources

| Alias | Назначение | Тип / формат | Поведение null | Пример |
| --- | --- | --- | --- | --- |
| `value` | Стабильное значение варианта, записываемое в Params | `string` / stable option key | Вариант отбрасывается | `"segment_a"` |
| `title` | Отображаемая подпись варианта | `string` / display label | Используется value | `"Сегмент A"` |

## Что менять

1. Замените только Meta и Sources, сохранив aliases.
2. Для необязательных подписей, палитры, единиц и форматов используйте блок CUSTOMIZE.

## Файлы

- [`meta.json`](code/ru/meta.json)
- [`params.js`](code/ru/params.js)
- [`sources.js`](code/ru/sources.js)
- [`controls.js`](code/ru/controls.js)
- [`schema.json`](code/ru/schema.json)
- [`example_input.json`](code/ru/example_input.json)
