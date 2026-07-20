# Архитектура

`datalens-dev-mcp` — локальный stdio MCP-сервер с исходящим клиентом DataLens API. MCP-клиент управляет жизненным циклом процесса. Сервер не открывает HTTP-порт.

## Поток данных

```text
Codex / Claude / другой MCP-клиент
  -> stdio JSON-RPC
  -> 38 инструментов MCP
  -> чтение / планирование / валидация / Safe Apply
  -> DataLens Public API

project root
  <-> требования, снимки, планы, контрольные чтения, отчёты

DATALENS_ENV_FILE
  -> ID организации, IAM-токен, write/save/publish-настройки
```

Stdout зарезервирован для MCP JSON-RPC. Логи и диагностика пишутся в stderr. Значения учётных данных не включаются в ответы и созданные файлы.

## Слои пакета

| Путь | Ответственность |
| --- | --- |
| `src/datalens_dev_mcp/server.py` | Инициализация MCP и диспетчер инструментов, prompts и resources |
| `src/datalens_dev_mcp/mcp/` | Контракты и реализации публичных инструментов |
| `src/datalens_dev_mcp/api/` | Авторизация, схемы методов, транспорт и очищенные ошибки |
| `src/datalens_dev_mcp/pipeline/` | Режим задачи, планы, Safe Apply, контрольные чтения и отчёты |
| `src/datalens_dev_mcp/editor/` | Сборка и проверка объектов Editor |
| `src/datalens_dev_mcp/validators/` | Проверка маршрутов, payload, SQL, связей, секретов и URI |
| `src/datalens_dev_mcp/knowledge/` | Компактный поиск по справочным данным DataLens |
| `src/datalens_dev_mcp/assets/` | Схемы, правила и шаблоны, входящие в Python-пакет |

## Границы безопасности

- Локальная папка проекта и live ID DataLens задаются отдельно.
- План не считается выполненной записью.
- Saved и published версии читаются и проверяются отдельно.
- Статическая проверка, чтение API и проверка интерфейса являются разными видами подтверждения.
- Перед записью сверяются цель и ревизия; публикация строится из saved readback.
- Произвольное удаление целого объекта недоступно; manifest action
  `retire_legacy_objects` требует отдельного подтверждения.

Подробности: [модель безопасности](local-only-safety-model.md), [Safe Apply](safe-apply.md), [выбор технологии](route-policy.md) и [контракты ответов](mcp/response_contracts.md).

## Поставка

Поддерживаемый формат поставки — Python-пакет с локальным stdio entrypoint. Все необходимые runtime-ресурсы входят в пакет. MCP-клиенты используют одинаковые command, args и env независимо от своего интерфейса.
