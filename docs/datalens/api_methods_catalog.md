# Каталог методов DataLens API

Полный актуальный каталог поставляется в `config/datalens_api_methods.json` и
доступен через `dl_list_api_methods`. Для одного метода используйте
`dl_get_api_method_schema`.

## Основные методы

| Объект | Методы чтения | Методы создания/обновления |
| --- | --- | --- |
| Workbook | `getWorkbooksList`, `getWorkbookEntries` | Обрабатываются проектным workflow при наличии manifest |
| Dashboard | `getDashboard` | `createDashboard`, `updateDashboard` |
| Wizard chart | `getWizardChart` | `createWizardChart`, `updateWizardChart` |
| Editor chart | `getEditorChart` | `createEditorChart`, `updateEditorChart` |
| QL chart | `getQLChart` | `createQLChart`, `updateQLChart` по прямому QL-запросу |
| Dataset | `getDataset` | `validateDataset`, `createDataset`, `updateDataset` |
| Connection | `getConnection` | `createConnection`, `updateConnection` |
| Relations | `getEntriesRelations` | — |

## Статусы

- `read_only` — метод используется для чтения или проверки;
- `guarded_write` — метод выполняется через target lock, fresh read, Safe Apply и readback;
- `reference_only` — контракт доступен для справки;
- `unsupported` — операция не входит в публичный workflow сервера.

Удаление целого объекта, когда оно поддержано выбранным project workflow,
требует отдельного `confirm_delete`. Перемещение и изменение permissions не
поддерживаются.

Официальные схемы и описания: [DataLens API Reference](https://yandex.cloud/ru/docs/datalens/openapi-ref/).
