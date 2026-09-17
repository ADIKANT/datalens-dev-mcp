# Покрытие DataLens API

[Официальный API Reference](https://yandex.cloud/ru/docs/datalens/openapi-ref/) · [Инструменты](../tools.md) · [Совместимость SDK](../testing/sdk-v3-compatibility.md)

Сервер использует SDK 3.0.0 и API v3. `tools/list` возвращает точные схемы закрытого набора typed-инструментов. `dl_method_schema` возвращает выбранные operation metadata, ограничения и ссылки; это не полная JSON Schema провайдера и не произвольный RPC gateway.

| Возможность | Публичный путь | Граница проверки |
| --- | --- | --- |
| Известный объект | `dl_object_get` | Тип, branch и ревизия; summary/projection не заменяют полный snapshot для замены |
| Workbook inventory | `dl_workbooks_list`, `dl_workbook_entries` | Ограниченные числовые страницы, явная неполнота и ошибки контейнера |
| Зависимости | `dl_object_relations`, `dl_dashboard_snapshot` | Прямые связи, opaque continuation; полнота обхода не гарантирует общий snapshot |
| История известного entry | `dl_object_revisions` | Одна страница по умолчанию 25, provider order, `rev_ids`, opaque continuation; отсутствие записи не доказывает неприменение |
| Dataset | `dl_dataset_validate`, `dl_dataset_preview` | Локальные проверки либо явная provider validation без сохранения; preview доказывает только запрос данных |
| Создание/изменение | `dl_object_create`, `dl_object_update` | Типизированный контракт, revision guards, saved readback и квитанция |
| Публикация | `dl_object_publish` | Свежая saved revision и published readback; отображение проверяется отдельно |
| Существующая вкладка dashboard | `dashboard_patch` в `dl_object_update` / `dl_object_diff` | Компактный delta по identity, сохранение соседних вкладок и связей |
| Неизвестный эффект | `dl_operation_get`, `dl_operation_reconcile` | Чтение доказательств без повтора записи; новый operation ID не разрешает retry |
| Удаление в заданном scope | `dl_cleanup_preview`, `dl_cleanup_apply` | Свежая dependency-safe preview, точный `confirmed_delete`, preserve checks и readback |

Wizard V1 get/update экспериментальны. Используются `data.sources` и visualization role slots; сохранение multi-dataset конфигурации не доказывает опубликованное исполнение. Схема `UpdateDashboardV2Args` относится к `/rpc/updateDashboard`, а canonical QL create называется `createQLChart`. Технологию существующего объекта следует сохранять; QL используется только по прямому запросу.

Standalone HTML Page authoring остаётся закрыт: `GetHtmlPageResult` содержит произвольный `data`, но не документирует чтение исходного HTML. Доступные metadata/publication не доказывают содержимое. HTML внутри Editor имеет отдельный контракт. В текущем Public API нет универсального `renderChart`/execution-log и операций mailing lists; новая UI-документация не создаёт такие возможности.

Проверен выбранный контракт из corpus 2026-09-17: 97 путей, OpenAPI SHA256 `13d9a6d48c4d932071b8d9ef81e81b8529b61a4534ae3747718eaa1dfecd21aa`. Это не утверждение поддержки всех путей или даты появления `getRevisions`. [Происхождение и область применения](../../skills/datalens-inspect/references/upstream-provenance.md).
