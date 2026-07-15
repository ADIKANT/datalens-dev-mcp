# Официальные источники

**Русский** · [English](sources_en.md) · [Главная](../README.md)

[Быстрый старт](../README.md#быстрый-старт) · [Доступ к DataLens](access.md) · [Подключение](codex_setup.md) · [Инструменты](tools.md) · [Сценарии](usage-flow.md) · **Источники** · [Безопасность](local-only-safety-model.md) · [English](sources_en.md)

Функциональность сервера опирается на официальную документацию DataLens, публичный OpenAPI-контракт и правила безопасного выполнения, реализованные в этом репозитории.

## Карта источников

| Область | Официальная страница | Как используется |
| --- | --- | --- |
| DataLens | [Документация DataLens](https://yandex.cloud/ru/docs/datalens/) | Термины, модель объектов и пользовательские возможности |
| Чарты | [Wizard, QL и Editor](https://yandex.cloud/ru/docs/datalens/concepts/chart/) | Выбор технологии и типов визуализации |
| Public API | [Начало работы с API](https://yandex.cloud/ru/docs/datalens/operations/api-start) | Адрес API, IAM-токен, ID организации и пример запроса |
| Методы API | [DataLens API Reference](https://yandex.cloud/ru/docs/datalens/openapi-ref/) | Имена методов, поля запросов и ответов |
| Editor | [Вкладки Editor](https://yandex.cloud/ru/docs/datalens/charts/editor/tabs) | Состав JavaScript-объекта Editor |
| Editor runtime | [Методы Editor](https://yandex.cloud/ru/docs/datalens/charts/editor/methods) | Проверка разрешённых вызовов `Editor.*` |
| Дашборды | [Устройство дашборда](https://yandex.cloud/ru/docs/datalens/concepts/dashboard/) | Вкладки, виджеты, селекторы, связи и компоновка |
| Воркбуки | [Воркбуки и коллекции](https://yandex.cloud/ru/docs/datalens/workbooks-collections/) | Расположение объектов и управление доступом |
| Датасеты | [Документация по датасетам](https://yandex.cloud/ru/docs/datalens/dataset/) | Поля, связи, вычисления и модель данных |
| Подключения | [Подключения](https://yandex.cloud/ru/docs/datalens/concepts/connection/) | Типы подключений и границы конфиденциальных настроек |
| Доступ | [Роли DataLens](https://yandex.cloud/ru/docs/datalens/security/roles) | Права на чтение, изменение и публикацию объектов |
| Лицензия документации | [CC BY 4.0 в yandex-cloud/docs](https://github.com/yandex-cloud/docs/blob/master/LICENSE) | Атрибуция адаптированных справочных данных |

## Три уровня функциональности

| Уровень | Что описывает | Где смотреть |
| --- | --- | --- |
| Возможности DataLens | Объекты, интерфейс, Editor и методы Public API | Официальные страницы выше |
| Реализация MCP | Доступные 38 инструментов, их входы и результаты | [Справочник инструментов](tools.md), [технический каталог](mcp/tools.md), [покрытие API](datalens/api_contract_coverage.md) |
| Правила выполнения | Выбор технологии чарта, проверка ревизии, сохранение, публикация и удаление | [Route policy](route-policy.md), [Safe Apply](safe-apply.md), [модель безопасности](local-only-safety-model.md) |

Перед выполнением операции сервер сверяет её с текущим каталогом методов и локальными правилами. Для проверки конкретного метода используйте `dl_list_api_methods` и `dl_get_api_method_schema`.

## Контракты Public API

Публичная OpenAPI-схема [`https://api.datalens.tech/json/`](https://api.datalens.tech/json/) используется как вход для компилятора схем. Из неё формируются компактные контракты валидации и каталог методов:

- [`config/datalens_api_methods.json`](../config/datalens_api_methods.json);
- [`config/datalens_api_operation_policy.json`](../config/datalens_api_operation_policy.json);
- [`schemas/datalens-api/source-trace.json`](../schemas/datalens-api/source-trace.json);
- [`docs/datalens/api_contract_coverage.md`](datalens/api_contract_coverage.md).

Пакет содержит скомпилированные контракты. `source-trace.json` хранит машинные данные, необходимые для проверки происхождения и воспроизводимости сборки.

## Справочные данные из документации

Официальный индекс `llms.txt` использован для поиска страниц документации. Документация Yandex Cloud распространяется по CC BY 4.0. Ссылки: [llms.txt](https://yandex.cloud/llms.txt), [лицензия yandex-cloud/docs](https://github.com/yandex-cloud/docs/blob/master/LICENSE).

Текст страниц был разобран, нормализован, сокращён до применимых правил и снабжён ссылками на оригиналы. Пакет содержит компактные индексы и схемы.

Машинные сведения о сборке находятся в:

- [`datalens-knowledge/PROVENANCE.json`](../src/datalens_dev_mcp/assets/schemas/datalens-knowledge/PROVENANCE.json);
- [`datalens-api/source-trace.json`](../schemas/datalens-api/source-trace.json).

Сервер использует эти локальные данные для `dl_reference`; во время обычной работы загрузка корпуса документации не выполняется.

## Лицензии и атрибуция

Код, схемы, шаблоны, тесты и оригинальная документация проекта лицензированы по [Apache License 2.0](../LICENSE). Адаптированное содержимое из документации Yandex Cloud сопровождается [CC BY 4.0](../LICENSES/CC-BY-4.0.txt) и указанием внесённых изменений.

Полные уведомления находятся в [`THIRD_PARTY_NOTICES.md`](../THIRD_PARTY_NOTICES.md), техническое описание происхождения — в [`source_provenance.md`](source_provenance.md).

Yandex Cloud, Yandex DataLens и связанные товарные знаки принадлежат их правообладателям.
