# Выбор технологии чарта

**Русский** · [English](route-policy_en.md) · [Инструменты](tools.md) · [Источники](sources.md)

Официальное описание технологий: [Wizard, QL и Editor](https://yandex.cloud/ru/docs/datalens/concepts/chart/). Версионированные правила сервера находятся в `config/route_selection_policy_v5.json`.

## Правила выбора

1. При обновлении сохраняется технология и `visualization_id` из актуальной saved-версии.
2. При создании учитывается прямое указание пользователя на Wizard, Editor или QL.
3. Editor используется для явно запрошенного JavaScript или возможностей, которых нет у подходящего Wizard-чарта.
4. Для стандартных визуализаций выбирается Wizard.
5. Ошибка API не приводит к автоматической смене технологии.

Решение содержит route, `visualization_id` и объяснение выбора.

## Стандартные визуализации Wizard

| Вид чарта | `visualization_id` |
| --- | --- |
| Показатель и показатель с дельтой | `metric` |
| Плоская таблица | `flatTable` |
| Сводная таблица | `pivotTable` |
| Линия | `line` |
| Область | `area`, `area100p` |
| Вертикальные столбцы | `column`, `column100p` |
| Горизонтальные столбцы | `bar`, `bar100p` |
| Комбинированный чарт | `combined-chart` |
| Круговая и кольцевая диаграмма | `pie`, `donut` |
| Точечная и пузырьковая диаграмма | `scatter` |
| Treemap | `treemap` |
| Карта | `geolayer` |

Для пузырьковой диаграммы требуется поле размера, для карты — подтверждённые геоданные. `wizard_map_native` нормализуется в `wizard_native` с `visualization_id=geolayer`.

## Editor

- `editor_advanced` — JavaScript-чарт общего назначения;
- `editor_table` — специализированная JavaScript-таблица;
- `editor_markdown` — Markdown-объект;
- `editor_js_control` — JavaScript-контрол.

Перед сохранением Editor-объект проходит `dl_validate_editor_runtime_contract` по официальным [вкладкам](https://yandex.cloud/ru/docs/datalens/charts/editor/tabs) и [методам](https://yandex.cloud/ru/docs/datalens/charts/editor/methods).

Явный проектный `authoring_profile: {"id": "standard_editor_v1"}` является
контрактом на JavaScript для всех поддержанных семейств. Он не меняет общий
Wizard-first default: профиль выбирает только зарегистрированный Editor-asset,
возвращает SHA-256 набора шаблонов, выбранных assets, style-контракта и
скомпилированных вкладок и запрещает приблизительный fallback. Если семейство
не зарегистрировано или требует native map, генерация через профиль блокируется.

Project-local профиль объявляется объектом с `id`, `descriptor_path` и
`descriptor_sha256`. Descriptor регистрирует только точные Editor-family
assets, сам и все зависимости остаются внутри project root, а fingerprint
полного template set проверяется до генерации. Такой профиль не расширяет
список поддержанных технологий и не разрешает fallback.

## QL

`ql_explicit` выбирается только по прямому запросу пользователя на QL. Создание и обновление используют явный payload или актуальную saved-версию QL-объекта. Сервер не генерирует QL по общему запросу и не выбирает его после ошибки Wizard или Editor.

## Создание и обновление

Для нового Wizard-чарта сервер предпочитает актуальный saved-образец с тем же `visualization_id`, удаляет идентификаторы исходного объекта и привязывает поля целевого датасета. При отсутствии образца используется встроенный канонический шаблон.

При update технология, визуализация, неизвестные поля и ревизия берутся из актуального чтения. Публикация регулируется [Safe Apply](safe-apply.md), независимо от выбранной технологии.
