# datalens-dev-mcp

**Русский** · [English](README_en.md)

[Быстрый старт](#быстрый-старт) · [Доступ к DataLens](docs/access.md) · [Подключение](#подключение-mcp-клиента) · [Инструменты](docs/tools.md) · [Сценарии](docs/usage-flow.md) · [Источники](docs/sources.md) · [Безопасность](docs/local-only-safety-model.md) · [Вся документация](docs/README.md) · [English](README_en.md)

`datalens-dev-mcp` — локальный Python-сервер [Model Context Protocol (MCP)](https://modelcontextprotocol.io/) для разработки дашбордов Yandex DataLens с помощью Codex, Claude и других MCP-клиентов. Сервер читает объекты DataLens, строит планы изменений, проверяет данные запроса, сохраняет изменения и публикует проверенную сохранённую версию.

MCP-клиент запускает сервер на вашем компьютере через stdio. Для работы с DataLens сервер обращается к [Public API](https://yandex.cloud/ru/docs/datalens/operations/api-start) с учётными данными пользователя. Входящие сетевые подключения, облачный посредник и телеметрия проекту не требуются.

> Это независимый проект сообщества. Он не относится к официальным продуктам Yandex или Yandex Cloud.

## Возможности

| Задача | Что делает сервер |
| --- | --- |
| Подключение | Проверяет локальную конфигурацию и реальный доступ к DataLens |
| Поиск объектов | Показывает воркбуки и их содержимое, читает связи между объектами |
| Аудит | Создаёт снимок дашборда со связанными чартами, датасетами и подключениями |
| Разработка | Планирует создание и обновление дашбордов, чартов, датасетов и подключений |
| HTML | Создаёт self-contained standalone HTML artifacts и проверяет sandbox без недокументированной загрузки |
| Единый JS-стиль | Переиспользует зарегистрированные Editor-шаблоны с SHA-256 и блокирует незарегистрированный fallback |
| Проверка | Проверяет схемы API, SQL, связи, селекторы, компоновку и код Editor |
| Применение | Выполняет актуальное чтение, сохраняет изменение, проверяет сохранённую версию, публикует её и проверяет результат |
| Справка | Даёт компактные ответы по возможностям DataLens и используемым методам API со ссылками на источники |

В стандартной конфигурации запись, сохранение и публикация доступны. Режим операции определяется формулировкой задачи:

- «проверь», «проанализируй», «проведи аудит» — только чтение;
- «составь план», `plan-only` — подготовка плана без записи;
- «сохрани без публикации», `save-only`, `no-publish` — сохранение и контрольное чтение;
- «создай», «исправь», «обнови», «переработай» — сохранение, контрольное чтение, публикация сохранённой версии и итоговая проверка;
- произвольное удаление целого объекта недоступно; объявленное в project
  manifest действие `retire_legacy_objects` требует отдельного подтверждения
  неизменившегося плана с точными ID.

[Справочник всех 38 инструментов](docs/tools.md) содержит назначение, входные данные и класс операции каждого вызова.

## Требования

- Python 3.11 или новее.
- Codex, Claude Code, Claude Desktop или другой MCP-клиент с поддержкой локального stdio-сервера.
- Для работы с DataLens: Yandex Cloud CLI, ID организации и права на нужный воркбук.

## Быстрый старт

```bash
git clone https://github.com/ADIKANT/datalens-dev-mcp.git
cd datalens-dev-mcp
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install .
.venv/bin/datalens-dev-mcp --version
python3 scripts/smoke_mcp_stdio.py
```

В Windows используйте `.venv\Scripts\python.exe` и `.venv\Scripts\datalens-dev-mcp.exe`. Для разработки самого сервера установите пакет командой `.venv/bin/python -m pip install -e '.[test]'`.

Затем настройте доступ по [пошаговой инструкции](docs/access.md). Минимальный защищённый env-файл выглядит так:

```dotenv
DATALENS_ORG_ID=<ID_ОРГАНИЗАЦИИ>
DATALENS_IAM_TOKEN=<IAM_ТОКЕН>
DATALENS_API_BASE_URL=https://api.datalens.tech
DATALENS_API_VERSION=auto
DATALENS_MCP_ENABLE_WRITES=1
DATALENS_MCP_LIVE_ALLOW_SAVE=1
DATALENS_MCP_LIVE_ALLOW_PUBLISH=1
DATALENS_ENABLE_TOKEN_REFRESH_ON_401=1
DATALENS_MCP_ENABLE_EXPERT_RPC=0
```

IAM-токен живёт ограниченное время. При настроенном `yc` сервер умеет получить начальный токен и обновить истёкший, после чего атомарно записывает его в указанный `DATALENS_ENV_FILE` с правами `0600`.

## Подключение MCP-клиента

Во всех примерах замените `/absolute/path/...` абсолютными путями. `--project-root` задаёт локальную папку для входных файлов, планов и отчётов. Идентификаторы воркбука, дашборда и других объектов передаются в задаче отдельно.

### Codex

Добавьте блок в `~/.codex/config.toml` или в `.codex/config.toml` доверенного проекта:

```toml
[mcp_servers.datalens_dev]
command = "/absolute/path/to/datalens-dev-mcp/.venv/bin/datalens-dev-mcp"
args = ["stdio", "--project-root", "/absolute/path/to/your/dashboard-project"]
cwd = "/absolute/path/to/your/dashboard-project"
env = { DATALENS_ENV_FILE = "/absolute/path/to/home/.config/datalens-dev-mcp/env" }
default_tools_approval_mode = "approve"
startup_timeout_sec = 20
tool_timeout_sec = 120
```

`default_tools_approval_mode = "approve"` разрешает Codex выполнять обычные вызовы этого MCP-сервера без дополнительного диалога перед сохранением и публикацией. Отдельное подтверждение применяется только к объявленному в project manifest действию `retire_legacy_objects`.

Ту же регистрацию можно выполнить командой:

```bash
codex mcp add datalens_dev \
  --env DATALENS_ENV_FILE=/absolute/path/to/home/.config/datalens-dev-mcp/env \
  -- /absolute/path/to/datalens-dev-mcp/.venv/bin/datalens-dev-mcp \
  stdio --project-root /absolute/path/to/your/dashboard-project
```

После регистрации проверьте `codex mcp list`, перезапустите Codex и откройте `/mcp`. Подробности: [настройка Codex](docs/codex_setup.md).

### Claude Code

```bash
claude mcp add --transport stdio --scope local \
  --env DATALENS_ENV_FILE=/absolute/path/to/home/.config/datalens-dev-mcp/env \
  datalens-dev -- \
  /absolute/path/to/datalens-dev-mcp/.venv/bin/datalens-dev-mcp \
  stdio --project-root /absolute/path/to/your/dashboard-project
```

Проверьте подключение командой `claude mcp list`.

### Claude Desktop и другие stdio-клиенты

```json
{
  "mcpServers": {
    "datalens-dev": {
      "command": "/absolute/path/to/datalens-dev-mcp/.venv/bin/datalens-dev-mcp",
      "args": ["stdio", "--project-root", "/absolute/path/to/your/dashboard-project"],
      "env": {
        "DATALENS_ENV_FILE": "/absolute/path/to/home/.config/datalens-dev-mcp/env"
      }
    }
  }
}
```

Готовые файлы находятся в [`examples/clients/`](examples/clients/).

## Первая сессия

Начните с проверки подключения:

> Используй DataLens MCP. Вызови `dl_runtime_status`, затем `dl_auth_probe`. Покажи, доступна ли запись, сохранение и публикация, и перечисли доступные воркбуки. На этом шаге работай только на чтение и не выводи учётные данные.

`dl_runtime_status` проверяет локальные настройки. `dl_auth_probe` выполняет минимальный реальный запрос `getWorkbooksList`. После успешной проверки можно вызвать `dl_get_workbook_entries`, `dl_snapshot_dashboard`, `dl_read_object` и `dl_get_entries_relations`.

Для изменения сформулируйте цель и укажите объект:

> Исправь чарт `<CHART_ID>` в воркбуке `<WORKBOOK_ID>`: `<ОПИСАНИЕ ИЗМЕНЕНИЯ>`. Сначала прочитай актуальную сохранённую версию и связи объекта, затем проверь план, сохрани изменение, выполни контрольное чтение, опубликуй сохранённую версию и проверь опубликованный результат.

Полный цикл и готовые формулировки для аудита, планирования, сохранения без публикации и обычного изменения приведены в [сценариях использования](docs/usage-flow.md).

## Безопасность изменений

Перед записью сервер проверяет точный объект, актуальную ревизию, схему запроса и связи. При обновлении сохраняются неизвестные поля и технология существующего чарта. Публикация строится из уже проверенной сохранённой версии, после неё выполняется отдельное контрольное чтение.

Параметры `DATALENS_MCP_ENABLE_WRITES`, `DATALENS_MCP_LIVE_ALLOW_SAVE` и `DATALENS_MCP_LIVE_ALLOW_PUBLISH` можно установить в `0`, чтобы жёстко отключить соответствующую возможность. Значение `0` имеет приоритет над формулировкой задачи.

Удаление легенды, фильтра, колонки, вкладки или виджета внутри объекта считается
обновлением. Стандартные lifecycle-инструменты не удаляют целые объекты;
поддерживается только project manifest action `retire_legacy_objects` с
двухшаговым подтверждением точных ID и неизменившегося плана. Удаление целого
QL-объекта не поддерживается.

Подробнее: [модель безопасности](docs/local-only-safety-model.md), [защищённое применение](docs/safe-apply.md) и [выбор технологии чарта](docs/route-policy.md).

## Устройство репозитория

| Путь | Назначение |
| --- | --- |
| `src/datalens_dev_mcp/` | Python-пакет, MCP-сервер, клиент DataLens API, планировщики и проверки |
| `config/` | Версионированные настройки поведения и выбора маршрутов |
| `schemas/` | JSON Schema для запросов, планов и отчётов |
| `templates/` | Шаблоны Wizard, Editor и проектных материалов |
| `docs/` | Руководства пользователя и техническая документация |
| `examples/` | Синтетические примеры и конфигурации MCP-клиентов |
| `scripts/` | Проверки, сборка пакета и обслуживание справочных данных |
| `tests/` | Модульные и интеграционные тесты без обращения к DataLens |

Архитектура описана в [`docs/architecture.md`](docs/architecture.md), локальная конфигурация — в [`docs/configuration.md`](docs/configuration.md).

## Разработка

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[test]'
python3 scripts/run_quick_checks.py
python3 scripts/run_offline_acceptance.py
```

Offline acceptance не требует учётных данных DataLens. Проверки с реальной записью выполняйте на специально выбранных объектах.

## Лицензия и источники

Код и оригинальная документация проекта распространяются по [Apache License 2.0](LICENSE). Справочные данные, адаптированные из документации Yandex Cloud, сопровождаются атрибуцией по [CC BY 4.0](LICENSES/CC-BY-4.0.txt). Перечень официальных страниц и способ их использования приведены в [`docs/sources.md`](docs/sources.md), полные уведомления — в [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md).
