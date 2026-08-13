# Диаграмма потоков

**Русский** · [English](README_en.md)

[← Cookbook](../../README.md) · [Web](https://adikant.github.io/datalens-dev-mcp/recipes/sankey/?lang=ru)

![Диаграмма потоков](preview.svg)

Потоки между узлами с шириной связей по объёму.

## Когда использовать

Маршруты перехода между несколькими состояниями.

## Особенности поведения

Геометрия содержит отдельные nodes и links; циклические связи не поддерживаются.

## Контракт Sources

| Alias | Назначение | Тип / формат | Поведение null | Пример |
| --- | --- | --- | --- | --- |
| `source` | Исходный узел потока | `string` / node label | Поток считается некорректным | `"Новый"` |
| `target` | Целевой узел потока | `string` / node label | Поток считается некорректным | `"В работе"` |
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
