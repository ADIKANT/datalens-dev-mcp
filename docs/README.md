# Документация datalens-dev-mcp 1.0

**Русский** · [English](README_en.md) · [Главная](../README.md)

`datalens-dev-mcp` — локальный Codex plugin и Python stdio backend для прямых типизированных операций Yandex DataLens. Модель выбирает одну из пяти предметных skills; сервер не содержит task compiler, journal или workflow engine.

## Актуальный контракт

- [Установка](installation.md) — wheel, plugin manifest и проверка вне checkout.
- [25 MCP-инструментов](tools.md) — закрытая поверхность чтения, authoring, записи и maintenance.
- [Карта visual consumers](authoring-property-consumers.md) — где именно применяются свойства рецептов и какая проверка ещё нужна.
- [Поддержанные SDK/API operations](../src/datalens_dev_mcp/schemas/supported-operations.json) — backend, версия и статическая граница каждого метода.
- [Карта 62 пользовательских результатов](../src/datalens_dev_mcp/schemas/capability-coverage.json) — прямой владелец и честная boundary, не исполняемый router.

## Предметные skills

- [Inspect](../skills/datalens-inspect/SKILL.md)
- [Dataset и Wizard](../skills/datalens-dataset-wizard/SKILL.md)
- [Editor](../skills/datalens-editor/SKILL.md)
- [Dashboard](../skills/datalens-dashboard/SKILL.md)
- [Maintenance](../skills/datalens-maintenance/SKILL.md)

Canonical runtime contract — `tools/list` установленного backend. Старые документы, не перечисленные в этом индексе, относятся к версиям до 1.0 и не определяют текущую поверхность или lifecycle.
