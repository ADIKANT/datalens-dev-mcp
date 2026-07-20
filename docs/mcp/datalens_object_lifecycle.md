# Жизненный цикл объектов DataLens

[Инструменты](../tools.md) · [Safe Apply](../safe-apply.md) · [API Reference](https://yandex.cloud/ru/docs/datalens/openapi-ref/)

## Чтение

- `dl_list_workbooks` — доступные воркбуки;
- `dl_get_workbook_entries` — объекты воркбука;
- `dl_read_object` — dashboard, Wizard chart, Editor chart, QL chart, dataset и connection по типу и ID;
- `dl_get_entries_relations` — связи между объектами;
- `dl_snapshot_dashboard` — дашборд и полный набор связанных объектов.

## Создание и обновление

`dl_plan_object_create` и `dl_plan_object_update` выбирают официальный API-метод и нормализуют payload. `dl_validate_object` проверяет форму запроса. Фактическая запись выполняется через Safe Apply.

Create использует расположение нового объекта и payload. Update начинается с актуальной saved-версии и сохраняет ID, ревизию, технологию чарта и неизвестные поля.

Для connection в `object_type` используется `connector` при планировании create/update и `connection` при чтении официального объекта API.

## Датасет

`dl_plan_guarded_dataset_update` моделирует последовательность:

1. актуальный `getDataset`;
2. `validateDataset`;
3. `updateDataset`, если задача требует изменения;
4. saved `getDataset` для контрольного чтения.

GUID полей сохраняются. Изменение GUID должно быть явно частью предлагаемой модели и проверяется по payload связанных чартов. Поля и вычисляемые поля изменяются внутри dataset payload, поскольку отдельного официального метода для них нет.

## Вкладка дашборда

`dl_plan_dashboard_tab_update` добавляет или заменяет одну вкладку поверх актуального dashboard payload. Остальные вкладки, metadata и координаты нетронутых виджетов сохраняются.

## Сохранение и публикация

`dl_create_safe_apply_plan` фиксирует режим задачи и target lock. `dl_execute_safe_apply` выполняет save после актуального чтения. `dl_readback_and_report` проверяет saved state.

Для обычного create/fix/update/enhance/redesign `dl_create_publish_from_saved_plan` строит publish из saved readback, затем executor выполняет его и отчёт проверяет published state. Save-only и no-publish останавливаются после saved readback.

## Удаление

Произвольное удаление целого объекта недоступно. Только manifest action
`retire_legacy_objects` требует отдельного `confirm_delete=true` для
неизменившегося плана с точными ID и связями. Удаление элемента внутри объекта
выполняется как update. Перемещение и изменение прав доступа не поддерживаются.
