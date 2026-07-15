# Документация datalens-dev-mcp

**Русский** · [English](README_en.md) · [Главная](../README.md)

[Установка](codex_setup.md) · [Инструменты](tools.md) · [Flow использования](usage-flow.md) · [Официальные источники](sources.md) · [Безопасность](local-only-safety-model.md)

Этот раздел объясняет публичную поверхность локального MCP-сервера: как его подключить, какие задачи решают 38 стандартных инструментов, как проходит работа от read-only проверки до guarded publish и какие официальные материалы DataLens лежат в основе API-контрактов и справочных registries.

## Начните отсюда

| Я хочу… | Откройте |
| --- | --- |
| Установить сервер и подключить Codex | [Настройка Codex](codex_setup.md) |
| Подключить Claude или другой stdio-клиент | [README: подключение MCP-клиента](../README.md#подключение-mcp-клиента) |
| Понять назначение конкретного инструмента | [Справочник 38 публичных инструментов](tools.md) |
| Провести read-only аудит дашборда | [Flow: чтение и snapshot](usage-flow.md#2-read-only-аудит) |
| Спланировать изменение без записи | [Flow: plan-only](usage-flow.md#3-plan-only) |
| Безопасно сохранить и опубликовать изменение | [Flow: guarded-save-и-publish](usage-flow.md#4-guarded-save-и-publish) |
| Проверить, на чем основана функция | [Карта официальных источников](sources.md) |
| Разобраться в блокировке записи | [Safe Apply](safe-apply.md) |
| Увидеть точные MCP inputs/outputs | [Технический tool catalog](mcp/tools.md) и [response contracts](mcp/response_contracts.md) |

## Основной пользовательский путь

```text
MCP client
  -> dl_runtime_status / dl_auth_probe
  -> workbook and object reads
  -> dashboard snapshot and relation evidence
  -> route, object, and project validation
  -> payload plan and safe-apply plan
  -> guarded save
  -> saved readback
  -> publish-from-saved when allowed
  -> published readback and runtime/browser QA
```

DataLens runtime по умолчанию read-only. Локальные tools могут создавать планы и отчеты внутри `--project-root`, но live mutation требует независимых write/save/publish gates, approval, fresh read и readback.

## Документация по темам

### Для пользователя

- [Инструменты](tools.md) — что делает каждый публичный tool и когда его вызывать.
- [Flow использования](usage-flow.md) — end-to-end сценарии и готовые prompts.
- [Настройка Codex](codex_setup.md) — app, CLI, `config.toml`, `/mcp` и troubleshooting.
- [Официальные источники](sources.md) — DataLens docs, Public API, Editor и provenance.

### Политика и безопасность

- [Конфигурация](configuration.md)
- [Local-only safety model](local-only-safety-model.md)
- [Route policy](route-policy.md)
- [Safe apply](safe-apply.md)
- [Policy vocabulary](policy_vocabulary.md)

### Техническая справка

- [Архитектура](architecture.md)
- [MCP tools](mcp/tools.md)
- [Response contracts](mcp/response_contracts.md)
- [Tool-selection policy](mcp/tool_selection_policy.md)
- [API contract coverage](datalens/api_contract_coverage.md)
- [Source provenance](source_provenance.md)

## Границы

- Обычный `tools/list` возвращает один стандартный набор из 38 инструментов.
- Compatibility/test-only tools не являются пользовательским профилем и не входят в рекомендуемый Flow.
- Wizard — default route для новых стандартных чартов; JavaScript используется по прямому запросу или capability gap; QL — только по прямому запросу.
- Delete, move и permission mutations закрыты для обычного workflow. Именованное удаление возможно только через отдельный `retire_legacy_objects` lifecycle.
- Сырые страницы документации, книги, курсы, private exports и credentials в репозитории не хранятся.
