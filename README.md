# datalens-dev-mcp

**Русский** · [English](README_en.md)

Публичный локальный MCP-плагин для разработки и сопровождения объектов Yandex DataLens. Версия 1.0 заменяет внутренний task workflow прямыми типизированными операциями: чтение, authoring, save/readback, publish-from-saved, backup и dependency-safe cleanup.

Плагин не является продуктом Yandex и работает только с правами текущего пользователя. Он не содержит языковую модель, Memory Bank, task compiler/journal, произвольный RPC/eval или browser-write fallback.

## Быстрый старт

Требуется Python 3.11+.

```bash
python3 -m venv .venv
.venv/bin/python -m pip install .
.venv/bin/datalens-dev-mcp --version
```

Подключение stdio описано в [.mcp.json](.mcp.json). Для live-доступа задайте собственные `DATALENS_ORG_ID` и `DATALENS_IAM_TOKEN`; значения credentials никогда не возвращаются инструментами.

## Предметный маршрут

- Inspect: точные ID, saved/published revision, pagination и прямые relations.
- Dataset/Wizard: реальные GUID, aggregation/formula restrictions и bounded `getDatasetData` preview.
- Editor: отдельные contracts для Table, Gravity, Advanced, Markdown и Selector; локальная проверка не выдаётся за browser runtime.
- Authoring: восемь versioned recipes — KPI, time comparison, bar, dynamic matrix, weekly totals, cross-tab, native table и selector. Большой JS берётся из canonical packaged renderer и сохраняется в локальный artifact; MCP по умолчанию возвращает компактный `draft_reference`. [Карта применяющих consumers](https://github.com/ADIKANT/datalens-dev-mcp/blob/main/docs/authoring-property-consumers.md) отделяет наличие настройки от runtime-доказательства.
- Delivery: create/update всегда заканчиваются saved readback. Publish — отдельная операция только из свежей saved revision с published readback.
- Maintenance: snapshot export честно помечен как не доказанный full restore; cleanup требует неизменившийся exact delete set.

Порядок defaults: generic → user → project → explicit reference → explicit call. Пользовательский файл: `${XDG_CONFIG_HOME:-~/.config}/datalens-dev-mcp/authoring.json`; проектный: `.datalens/authoring.json`.

## SDK и API

Официальный `datalens-sdk==0.9.0` используется для поддержанных typed операций. Точечный Public API adapter остаётся для `getDatasetData`, relations, HTML Page и license endpoints. MCP и публичный модуль `datalens_dev_mcp.sdk` вызывают одни и те же сервисы.

`.build()` и `.execute()` выполняют внешнюю запись. Pure authoring (`dl_compile_recipe`) сети не вызывает. SDK raw replace применяется только после fresh read и narrow semantic merge; серверной общей CAS/транзакции для batch не обещается.

## Основные ограничения

- Dataset и Connection не получают выдуманный publish lifecycle.
- Wizard, Editor и QL не взаимозаменяются автоматически; update сохраняет технологию.
- `getDatasetData` подтверждает Dataset-backed данные, но не Editor runtime и не published branch.
- Browser используется read-only, когда задача требует rendered evidence, после API/readback и применимой проверки данных.
- Неоднозначная потеря ответа не повторяет write: используется `dl_operation_reconcile` по известному ID/revision.
- License revoke и общий ACL mutation не заявлены как поддержанные.

Полный tools/list возвращает закрытые JSON Schemas. Карта 62 пользовательских случаев находится в `datalens_dev_mcp/schemas/capability-coverage.json`. Пять bundled skills загружают только нужные references.

## Разработка

```bash
.venv/bin/python -m pip install -e '.[test]'
.venv/bin/pytest -q tests/replacement
python -m build
```

Лицензия: Apache-2.0 для кода; дополнительные условия и атрибуции см. в [NOTICE](NOTICE), [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) и [LICENSES](LICENSES).
