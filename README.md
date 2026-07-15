# datalens-dev-mcp

**Русский** · [English](README_en.md)

[Установка](#установка) · [Инструменты](docs/tools.md) · [Flow использования](docs/usage-flow.md) · [Официальные источники](docs/sources.md) · [Безопасность](docs/local-only-safety-model.md) · [Вся документация](docs/README.md)

`datalens-dev-mcp` — локальный Python-сервер [Model Context Protocol (MCP)](https://modelcontextprotocol.io/) для разработки дашбордов Yandex DataLens с помощью ИИ. Он дает Codex, Claude и другим MCP-клиентам управляемый набор инструментов для чтения объектов DataLens, планирования изменений, проверки payload и безопасного применения согласованных изменений.

Сервер работает через stdio: MCP-клиент запускает его дочерним процессом на вашем компьютере. В репозитории нет hosted-сервиса, учетной записи или endpoint телеметрии. Для live-операций сервер подключается с вашего компьютера к настроенному DataLens Public API.

> Это независимый проект сообщества. Он не является официальным продуктом Yandex или Yandex Cloud и не поддерживается от их имени.

## Что умеет сервер

| Задача | Возможности |
| --- | --- |
| Подключение и диагностика | Проверка runtime-конфигурации, наличия credentials и минимальный auth probe без вывода секретов |
| Чтение DataLens | Workbooks, entries, связи объектов, дашборды, чарты, датасеты и подключения |
| Планирование | Wizard-first создание и обновление объектов, Advanced Editor для явного запроса или зарегистрированного capability gap, QL только по прямому запросу |
| Валидация | Payload, маршруты, связи, селекторы, layout, SQL, Editor runtime и source availability |
| Изменения | Guarded safe apply: fresh read, сохранение revision, save, saved readback, отдельный publish-from-saved и published readback |
| Аудит | Снимки графа дашборда, deployment reports и явные proof levels для static/API/save/publish/browser evidence |
| Справка | Компактные source-traced данные, собранные из открытой документации DataLens и Public API |

Обычная работа начинается в read-only режиме. Локальные planning tools могут создавать артефакты внутри `--project-root`, но запись в DataLens по умолчанию отключена.

- [Описание всех 38 публичных инструментов](docs/tools.md)
- [Полный Flow от подключения до runtime QA](docs/usage-flow.md)
- [Карта официальной документации и API-источников](docs/sources.md)
- [Технический MCP-каталог и response contracts](docs/mcp/tools.md)

## Требования

- Python 3.11 или новее.
- MCP-клиент с поддержкой локального stdio-сервера: Codex, Claude Code, Claude Desktop или другой совместимый клиент.
- Для live-чтения: ID организации Yandex Cloud и IAM-токен с доступом к целевым объектам.

## Установка

```bash
git clone https://github.com/ADIKANT/datalens-dev-mcp.git
cd datalens-dev-mcp
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install .
.venv/bin/datalens-dev-mcp --version
python3 scripts/smoke_mcp_stdio.py
```

В Windows используйте `.venv\Scripts\python.exe` и `.venv\Scripts\datalens-dev-mcp.exe`. Для разработки самого сервера установите пакет командой `pip install -e .`.

## Credentials

Для offline-планирования credentials не нужны. Для live-чтения создайте env-файл вне репозитория:

```bash
mkdir -p ~/.config/datalens-dev-mcp
touch ~/.config/datalens-dev-mcp/env
chmod 600 ~/.config/datalens-dev-mcp/env
```

```dotenv
DATALENS_ORG_ID=<YOUR_ORG_ID>
DATALENS_IAM_TOKEN=<YOUR_IAM_TOKEN>
DATALENS_API_BASE_URL=https://api.datalens.tech
DATALENS_API_VERSION=auto

# Для первого запуска оставьте все mutation gates выключенными.
DATALENS_MCP_ENABLE_WRITES=0
DATALENS_MCP_LIVE_ALLOW_SAVE=0
DATALENS_MCP_LIVE_ALLOW_PUBLISH=0
DATALENS_MCP_ENABLE_EXPERT_RPC=0
```

Вместо `DATALENS_IAM_TOKEN` можно использовать `YC_IAM_TOKEN`. Передавайте клиенту только абсолютный путь к env-файлу. Не помещайте токен в MCP arguments, prompts, tracked config, logs или issue reports.

## Подключение MCP-клиента

Замените все `/absolute/path/...`. `--project-root` — локальная директория, где сервер читает входные файлы проекта и сохраняет артефакты. Она не выбирает workbook или dashboard: live ID всегда передаются отдельно.

Готовые примеры находятся в [`examples/clients/`](examples/clients/).

### Codex

Добавьте в `~/.codex/config.toml` или в `.codex/config.toml` доверенного проекта:

```toml
[mcp_servers.datalens_dev]
command = "/absolute/path/to/datalens-dev-mcp/.venv/bin/datalens-dev-mcp"
args = ["stdio", "--project-root", "/absolute/path/to/your/dashboard-project"]
cwd = "/absolute/path/to/your/dashboard-project"
env = { DATALENS_ENV_FILE = "/absolute/path/to/home/.config/datalens-dev-mcp/env" }
```

Или зарегистрируйте сервер через CLI:

```bash
codex mcp add datalens-dev \
  --env DATALENS_ENV_FILE=/absolute/path/to/home/.config/datalens-dev-mcp/env \
  -- /absolute/path/to/datalens-dev-mcp/.venv/bin/datalens-dev-mcp \
  stdio --project-root /absolute/path/to/your/dashboard-project
```

Проверьте `codex mcp list`, перезапустите Codex и откройте `/mcp`. Полная инструкция: [`docs/codex_setup.md`](docs/codex_setup.md).

### Claude Code

```bash
claude mcp add --transport stdio --scope local \
  --env DATALENS_ENV_FILE=/absolute/path/to/home/.config/datalens-dev-mcp/env \
  datalens-dev -- \
  /absolute/path/to/datalens-dev-mcp/.venv/bin/datalens-dev-mcp \
  stdio --project-root /absolute/path/to/your/dashboard-project
```

Проверьте регистрацию командой `claude mcp list`.

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

Для generic-клиента используйте значения `command`, `args` и `env` из вложенного объекта. Процесс обменивается JSON-RPC через stdin/stdout; HTTP endpoint отсутствует. Диагностика идет в stderr.

## Первая read-only сессия

Попросите клиента выполнить:

1. `dl_runtime_status` и проверку, что `allow_writes`, `allow_save` и `allow_publish` равны `false`.
2. `dl_auth_probe` для минимального безопасного live-read.
3. `dl_list_workbooks`, затем `dl_get_workbook_entries` для выбранного workbook.
4. `dl_snapshot_dashboard` перед планированием изменения существующего дашборда.

Готовый prompt:

> Используй DataLens MCP server. Сначала покажи `dl_runtime_status` и проверь, что все mutation gates выключены. Затем выполни `dl_auth_probe` и перечисли доступные workbooks. Ничего не сохраняй, не публикуй и не изменяй.

Дальнейшие сценарии, включая plan-only, save-only и guarded publish, приведены в [руководстве по Flow](docs/usage-flow.md).

## Безопасность записи

`DATALENS_MCP_ENABLE_WRITES=1` открывает только один runtime gate. Для изменения по-прежнему нужны:

1. Известный target и fresh saved readback.
2. Проверенный payload и approved safe-apply plan.
3. Сохранение revision, неизвестных полей и технологии объекта.
4. Save и отдельный saved readback.
5. Publish-from-saved только при соответствующем delivery intent и включенном publish gate.
6. Published readback, deployment report и runtime/browser proof для видимых изменений.

Planning, review, draft, save-only и no-publish блокируют публикацию. QL используется только после прямого запроса. Delete, move и permission operations не входят в обычный write path.

Подробнее: [safety model](docs/local-only-safety-model.md), [safe apply](docs/safe-apply.md) и [route policy](docs/route-policy.md).

## Устройство репозитория

| Путь | Назначение |
| --- | --- |
| `src/datalens_dev_mcp/` | Python package, MCP dispatcher, tools, API client, pipeline, validators и packaged resources |
| `config/` | Версионированные safe defaults, route policy, style и API metadata |
| `schemas/` | JSON Schemas для project artifacts и validation |
| `templates/` | Wizard, Advanced Editor, requirements и project templates |
| `docs/` | Центр документации, guides, safety, API и технические contracts |
| `examples/` | Синтетические inputs и конфигурации MCP-клиентов |
| `scripts/` | Offline acceptance, smoke, packaging и maintenance checks |
| `tests/` | Unit и offline integration tests |

Архитектура и trust boundaries описаны в [`docs/architecture.md`](docs/architecture.md). Локальную конфигурацию см. в [`docs/configuration.md`](docs/configuration.md).

## Разработка

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[test]'
python3 scripts/run_quick_checks.py
python3 scripts/run_offline_acceptance.py
```

Acceptance suite работает offline и не требует DataLens credentials. Live-проверки являются opt-in и должны использовать disposable targets.

## Лицензия и атрибуция

Код и оригинальная документация проекта распространяются по Apache License 2.0: [`LICENSE`](LICENSE). Справочные данные, адаптированные из документации Yandex Cloud, атрибутированы по CC BY 4.0: [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md). Подробная карта источников находится в [`docs/sources.md`](docs/sources.md).
