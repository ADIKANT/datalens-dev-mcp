# Контракт DataLens API

Официальный источник:
[DataLens API Reference](https://yandex.cloud/ru/docs/datalens/openapi-ref/).
Сведения о компиляции схем: [`docs/sources.md`](../sources.md).

## Транспорт

- Методы вызываются через `POST https://api.datalens.tech/rpc/<method>`.
- Запрос содержит `Authorization: Bearer <IAM_TOKEN>`, `x-dl-org-id`,
  `x-dl-api-version`, `content-type: application/json` и
  `accept: application/json`.
- `DATALENS_API_VERSION=auto` выбирает версию, закреплённую в скомпилированном контракте.
- Диагностика очищается от токенов, заголовков авторизации, паролей и закрытых ключей.

## Статус метода

Каталог разделяет методы чтения, методы записи через Safe Apply и справочные
операции. Текущий статус можно получить через `dl_list_api_methods`, точную
схему — через `dl_get_api_method_schema`.

## Запись

Перед write выполняются target lock, актуальное чтение, сохранение ревизии и
неизвестных полей, валидация payload и проверка write/save/publish. Save
сопровождается saved readback. Publish строится из saved readback и
сопровождается published readback.

Команда пользователя на create/fix/update/enhance/redesign запускает этот цикл
без отдельного подтверждения save/publish. Удаление целого объекта использует
отдельный `confirm_delete` flow. Перемещение, изменение прав и credential
mutations не поддерживаются.

Повтор записи под другой API-версией не выполняется.
