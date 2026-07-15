# Официальные источники и provenance

**Русский** · [English](sources_en.md) · [Документация](README.md) · [Инструменты](tools.md)

`datalens-dev-mcp` не является зеркалом документации. Runtime состоит из project-authored кода и правил, а компактные справочные registries и API schemas собраны из публичных первичных источников с сохранением source metadata.

## Три слоя истины

| Слой | Что он определяет | Где смотреть |
| --- | --- | --- |
| Официальная документация DataLens | Публичную модель объектов, возможности UI, Editor, Public API и требования авторизации | Ссылки ниже |
| Реализация MCP | Какие чтения, planners, validators и guarded executors реально доступны | [`server.py`](../src/datalens_dev_mcp/server.py), [справочник инструментов](tools.md), [API coverage](datalens/api_contract_coverage.md) |
| Локальная policy | Wizard-first routing, QL explicit-only, save/readback/publish gates и закрытые destructive routes | [Route policy](route-policy.md), [Safe Apply](safe-apply.md), [Safety model](local-only-safety-model.md) |

Наличие функции в документации DataLens не означает, что MCP разрешает ее выполнять. Статус конкретной операции проверяется через `dl_list_api_methods`, `dl_get_api_method_schema`, `dl_reference(mode="api_contract")` и локальную policy.

## Основные официальные страницы

| Область | Первичный источник | Как используется проектом |
| --- | --- | --- |
| DataLens в целом | [Документация DataLens](https://yandex.cloud/ru/docs/datalens/) и [обзор сервиса](https://yandex.cloud/ru/docs/datalens/concepts/) | Термины, object model и пользовательские возможности |
| Начало работы | [Quickstart](https://yandex.cloud/ru/docs/datalens/quickstart) | Связь connection → dataset → chart → dashboard |
| Типы чартов | [Chart concept](https://yandex.cloud/ru/docs/datalens/concepts/chart/) | Различие Wizard, QL и Editor; локальная policy дополнительно ограничивает выбор route |
| Public API | [Работа с Public API](https://yandex.cloud/ru/docs/datalens/operations/api-start) | Base URL, IAM authentication, organization context и общая модель RPC |
| API methods | [DataLens API Reference](https://yandex.cloud/ru/docs/datalens/openapi-ref/) | Method names, request/response fields и ссылки из локального API catalog |
| Workbooks и collections | [Workbooks and collections](https://yandex.cloud/ru/docs/datalens/workbooks-collections/) | Контейнеры объектов и object location semantics |
| Connections | [Connections](https://yandex.cloud/ru/docs/datalens/concepts/connection/) | Модель подключения и sensitive configuration boundaries |
| Datasets | [Dataset concept](https://yandex.cloud/ru/docs/datalens/dataset/) | Поля, joins, calculations и dataset-owned changes |
| Wizard | [Creating a chart](https://yandex.cloud/ru/docs/datalens/operations/chart/create-chart) | Native chart semantics; MCP выбирает Wizard для стандартных новых чартов |
| Editor | [Editor overview](https://yandex.cloud/ru/docs/datalens/charts/editor/) | JavaScript authoring model и runtime boundary |
| Editor tabs | [Editor tabs](https://yandex.cloud/ru/docs/datalens/charts/editor/tabs) | `Meta`, `Params`, `Sources`, `Prepare`, `Config`, `Controls`, `Activities` |
| Editor methods | [Editor methods](https://yandex.cloud/ru/docs/datalens/charts/editor/methods) | Allowlist и runtime validation для `Editor.*` methods |
| Dashboards | [Dashboard concept](https://yandex.cloud/ru/docs/datalens/concepts/dashboard/) | Tabs, widgets, selectors, links и layout |
| Access | [DataLens security](https://yandex.cloud/ru/docs/datalens/security/) | Read-only guidance; normal MCP workflow не включает permission mutations |

## Public API contracts

Публичный OpenAPI response [`https://api.datalens.tech/json/`](https://api.datalens.tech/json/) используется как детерминированный compiler input. Сырой OpenAPI-файл не распространяется в package. Из него собираются нормализованные interoperability contracts; prose annotations удаляются.

Для конкретного MCP-инструмента связь с official method приведена в [справочнике инструментов](tools.md). Полная локальная матрица находится в:

- [`config/datalens_api_methods.json`](../config/datalens_api_methods.json);
- [`config/datalens_api_operation_policy.json`](../config/datalens_api_operation_policy.json);
- [`schemas/datalens-api/source-trace.json`](../schemas/datalens-api/source-trace.json);
- [`docs/datalens/api_contract_coverage.md`](datalens/api_contract_coverage.md).

## Документационный snapshot

Для discovery machine-readable страниц использовался [`https://yandex.cloud/llms.txt`](https://yandex.cloud/llms.txt). Это только указатель на документацию, а не лицензия и не самостоятельное разрешение на распространение.

Текущий упакованный knowledge snapshot:

- generated at: `2026-07-13T13:43:44Z`;
- pages content SHA-256: `fda97edaac019a8f7c74376c7918da5cffb12214cf87de106b7356a59ddccfaf`;
- OpenAPI SHA-256: `e4c3cf56de894e28b883b1f0ceaf2935f68570b052c46885e20bc9608e5ca532`.

Машиночитаемые источники этих значений:

- [`datalens-knowledge/PROVENANCE.json`](../src/datalens_dev_mcp/assets/schemas/datalens-knowledge/PROVENANCE.json);
- [`datalens-api/source-trace.json`](../schemas/datalens-api/source-trace.json).

При следующей регенерации checker должен сверять опубликованные значения с этими файлами, чтобы документация не расходилась с package assets.

## Лицензии и изменения

Официальный repository [`yandex-cloud/docs`](https://github.com/yandex-cloud/docs) публикует документацию по [Creative Commons Attribution 4.0 International](https://github.com/yandex-cloud/docs/blob/master/LICENSE). Адаптированные records были parsed, normalized, indexed, excerpted, summarized и deduplicated; full site mirror и images в репозитории отсутствуют.

Код, schemas, templates, tests, локальная policy и project-authored документация лицензированы по Apache License 2.0. CC BY 4.0 применяется только к адаптированному документационному содержимому. Полные notices: [`THIRD_PARTY_NOTICES.md`](../THIRD_PARTY_NOTICES.md), [`LICENSES/CC-BY-4.0.txt`](../LICENSES/CC-BY-4.0.txt) и [source provenance](source_provenance.md).

Yandex Cloud, Yandex DataLens и связанные marks принадлежат их правообладателям. Их использование здесь носит описательный характер; endorsement не подразумевается.
