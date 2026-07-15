# Покрытие DataLens API

[Официальный API Reference](https://yandex.cloud/ru/docs/datalens/openapi-ref/) · [Источники](../sources.md) · [Инструменты](../tools.md)

Сервер компилирует публичную OpenAPI-схему в локальный каталог методов и JSON Schema. Актуальная установленная версия доступна через:

- `dl_list_api_methods` — методы, режим и статус поддержки;
- `dl_get_api_method_schema` — обязательные поля, request/response schema и URL официальной страницы;
- `dl_validate_object` — проверка payload;
- `dl_plan_object_create` и `dl_plan_object_update` — подготовка create/update;
- `dl_compile_guarded_rpc_request` — target lock, ревизия и ожидаемое контрольное чтение.

## Покрытые семейства

| Семейство | Чтение | Создание и обновление | Примечание |
| --- | --- | --- | --- |
| Workbooks | `dl_list_workbooks`, `dl_get_workbook_entries` | Project manifest | Контейнер объектов |
| Dashboards | `dl_read_object`, `dl_snapshot_dashboard` | Object plan + Safe Apply | `dl_plan_dashboard_tab_update` для вкладок |
| Wizard charts | `dl_read_object` | Generic object plan + Safe Apply | Стандартные визуализации используют Wizard |
| Editor charts | `dl_read_object` | Generic object plan + Safe Apply | Код дополнительно проверяет `dl_validate_editor_runtime_contract` |
| QL charts | `dl_read_object` | Generic object plan после прямого QL-запроса | QL не выбирается автоматически |
| Datasets | `dl_read_object` | `dl_plan_guarded_dataset_update` + Safe Apply | Проверяются GUID и связанные чарты |
| Connections | `dl_read_object` | Generic object plan + Safe Apply | Секретные поля очищаются |
| Relations | `dl_get_entries_relations` | Изменяются внутри поддерживаемого object payload | Используются для target и delete checks |

## Операции записи

Create/update выполняются через plan, актуальное чтение, валидацию, save и saved readback.
Обычная задача на реализацию продолжается через publish-from-saved и published readback.

Удаление целого поддерживаемого объекта требует `confirm_delete=true` для неизменившегося плана с точными ID.
Перемещение, изменение прав доступа, лицензий и учётных данных не поддерживаются.

Машинный trace с данными сборки находится в [`schemas/datalens-api/source-trace.json`](../../schemas/datalens-api/source-trace.json).
