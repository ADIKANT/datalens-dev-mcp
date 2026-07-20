# Связь инструментов с DataLens API

| Инструменты MCP | Официальные методы | Использование |
| --- | --- | --- |
| `dl_list_workbooks`, `dl_get_workbook_entries` | `getWorkbooksList`, `getWorkbookEntries` | Поиск воркбуков и объектов |
| `dl_get_entries_relations` | `getEntriesRelations` | Связи объектов |
| `dl_read_object` | `getDashboard`, `get*Chart`, `getDataset`, `getConnection` | Унифицированное чтение |
| `dl_plan_object_create` | create-метод выбранного object type | План создания |
| `dl_plan_object_update` | update-метод выбранного object type | План обновления |
| `dl_plan_guarded_dataset_update` | `getDataset`, `validateDataset`, `updateDataset` | Проверка и обновление датасета |
| `dl_create_safe_apply_plan`, `dl_execute_safe_apply` | Методы записи из проверенного плана | Save-first применение |
| `dl_create_publish_from_saved_plan` | Update-метод в publish mode | Публикация из saved readback |
| `dl_list_api_methods`, `dl_get_api_method_schema` | OpenAPI catalog | Справка по контрактам |

Точный метод и request schema возвращаются plan-инструментом до выполнения
записи. Официальный источник:
[DataLens API Reference](https://yandex.cloud/ru/docs/datalens/openapi-ref/).
