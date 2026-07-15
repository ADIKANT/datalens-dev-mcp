# datalens-dev-mcp

[English version](README.md)

`datalens-dev-mcp` — локальный Python-сервер [Model Context Protocol (MCP)](https://modelcontextprotocol.io/) для разработки дашбордов Yandex DataLens с помощью ИИ. Он дает MCP-клиентам управляемый набор инструментов для чтения объектов DataLens, проектирования дашбордов и чартов, проверки payload и применения согласованных изменений через защищенный цикл save/readback.

Сервер работает через stdio: MCP-клиент запускает его дочерним процессом на вашем компьютере. В репозитории нет hosted-сервиса, учетной записи или endpoint телеметрии. Для live-операций сервер подключается с вашего компьютера к настроенному DataLens API.

> Это независимый проект сообщества. Он не является официальным продуктом Yandex или Yandex Cloud и не поддерживается от их имени.

## Возможности

- Читает workbooks, workbook entries, связи объектов, дашборды, чарты, датасеты и подключения через DataLens API-клиент с безопасной обработкой ошибок.
- Строит детерминированные планы для native Wizard-чартов и зарегистрированных сценариев Advanced Editor.
- Проверяет маршруты, роли полей, связи дашборда, селекторы, layout, технические имена, Editor bundles и сгенерированный SQL.
- Ведет локальную рабочую область проекта с требованиями, планами реализации, проверками и отчетами о развертывании.
- Перед изменениями создает свежие снимки и сохраняет технологию и revision существующих объектов.
- Держит live-запись за явными runtime-флагами, согласованным safe-apply планом, save-first семантикой и readback.
- Использует упакованные справочные данные DataLens, собранные из открытой документации; источники и условия лицензирования указаны в `THIRD_PARTY_NOTICES.md`.

По умолчанию DataLens runtime работает только на чтение. При этом локальные planning tools могут создавать артефакты проекта в директории, переданной через `--project-root`. Offline-планирование и валидация доступны без учетных данных DataLens.

## Требования

- Python 3.11 или новее.
- MCP-клиент, который умеет запускать локальный stdio-сервер: Codex, Claude Code, Claude Desktop или другой совместимый инструмент.
- Для live-чтения DataLens: ID организации Yandex Cloud и IAM-токен с доступом к нужным объектам.

## Установка из исходного кода

```bash
git clone https://github.com/ADIKANT/datalens-dev-mcp.git
cd datalens-dev-mcp
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install .
.venv/bin/datalens-dev-mcp --version
python3 scripts/smoke_mcp_stdio.py
```

В Windows используйте `.venv\Scripts\python.exe` и `.venv\Scripts\datalens-dev-mcp.exe` вместо POSIX-путей выше.

Для разработки самого сервера устанавливайте его командой `pip install -e .`.

## Настройка учетных данных

Для offline-инструментов учетные данные не нужны. Для live-чтения создайте env-файл вне репозитория:

```bash
mkdir -p ~/.config/datalens-dev-mcp
touch ~/.config/datalens-dev-mcp/env
chmod 600 ~/.config/datalens-dev-mcp/env
```

Добавьте свои значения и не коммитьте файл:

```dotenv
DATALENS_ORG_ID=<YOUR_ORG_ID>
DATALENS_IAM_TOKEN=<YOUR_IAM_TOKEN>
DATALENS_API_BASE_URL=https://api.datalens.tech
DATALENS_API_VERSION=auto

# Для первого запуска оставьте все gates изменения выключенными.
DATALENS_MCP_ENABLE_WRITES=0
DATALENS_MCP_LIVE_ALLOW_SAVE=0
DATALENS_MCP_LIVE_ALLOW_PUBLISH=0
DATALENS_MCP_ENABLE_EXPERT_RPC=0
```

Вместо `DATALENS_IAM_TOKEN` можно использовать `YC_IAM_TOKEN`. В конфигурации клиента укажите абсолютный путь к env-файлу. Не передавайте токен в аргументах MCP, промптах, tracked-конфигах или отчетах об ошибках.

## Подключение MCP-клиента

Замените все значения `/absolute/path/...`. Параметр `--project-root` задает локальную директорию, в которой сервер читает входные данные проекта и может сохранять сгенерированные артефакты. Это может быть сам checkout или отдельный проект дашборда.

Готовые файлы конфигурации находятся в [`examples/clients/`](examples/clients/).

### Codex

Добавьте в `~/.codex/config.toml`:

```toml
[mcp_servers.datalens_dev]
command = "/absolute/path/to/datalens-dev-mcp/.venv/bin/datalens-dev-mcp"
args = ["stdio", "--project-root", "/absolute/path/to/your/dashboard-project"]
cwd = "/absolute/path/to/your/dashboard-project"
env = { DATALENS_ENV_FILE = "/absolute/path/to/home/.config/datalens-dev-mcp/env" }
```

Тот же сервер можно зарегистрировать через Codex CLI:

```bash
codex mcp add datalens-dev \
  --env DATALENS_ENV_FILE=/absolute/path/to/home/.config/datalens-dev-mcp/env \
  -- /absolute/path/to/datalens-dev-mcp/.venv/bin/datalens-dev-mcp \
  stdio --project-root /absolute/path/to/your/dashboard-project
```

После изменения конфигурации перезапустите Codex. Проверка и диагностика описаны в [`docs/mcp/codex_connection.md`](docs/mcp/codex_connection.md).

### Claude Code

Выполните команду из директории проекта дашборда:

```bash
claude mcp add --transport stdio --scope local \
  --env DATALENS_ENV_FILE=/absolute/path/to/home/.config/datalens-dev-mcp/env \
  datalens-dev -- \
  /absolute/path/to/datalens-dev-mcp/.venv/bin/datalens-dev-mcp \
  stdio --project-root /absolute/path/to/your/dashboard-project
```

Проверьте регистрацию командой `claude mcp list`.

### Claude Desktop

Добавьте сервер в объект `mcpServers` файла `claude_desktop_config.json`. По умолчанию он находится в `~/Library/Application Support/Claude/claude_desktop_config.json` на macOS и `%APPDATA%\Claude\claude_desktop_config.json` в Windows:

```json
{
  "mcpServers": {
    "datalens-dev": {
      "command": "/absolute/path/to/datalens-dev-mcp/.venv/bin/datalens-dev-mcp",
      "args": [
        "stdio",
        "--project-root",
        "/absolute/path/to/your/dashboard-project"
      ],
      "env": {
        "DATALENS_ENV_FILE": "/absolute/path/to/home/.config/datalens-dev-mcp/env"
      }
    }
  }
}
```

После сохранения файла перезапустите Claude Desktop.

### Другие stdio-клиенты

Для клиента с полями MCP command, args и env используйте такое описание процесса:

```json
{
  "command": "/absolute/path/to/datalens-dev-mcp/.venv/bin/datalens-dev-mcp",
  "args": [
    "stdio",
    "--project-root",
    "/absolute/path/to/your/dashboard-project"
  ],
  "env": {
    "DATALENS_ENV_FILE": "/absolute/path/to/home/.config/datalens-dev-mcp/env"
  }
}
```

Процесс обменивается JSON-RPC сообщениями через stdin/stdout; HTTP endpoint нет. Диагностика сервера идет в stderr, а stdout зарезервирован для MCP-сообщений.

## Первая read-only сессия

После подключения клиента попросите его последовательно выполнить:

1. Вызвать `dl_runtime_status` и убедиться, что `allow_writes`, `allow_save` и `allow_publish` равны `false`.
2. Вызвать `dl_auth_probe`. Без учетных данных ожидается безопасный blocked-результат; с корректными данными инструмент выполнит минимальное чтение.
3. Вызвать `dl_list_workbooks`, затем `dl_get_workbook_entries` для доступного workbook.
4. Перед планированием изменений существующего дашборда вызвать `dl_snapshot_dashboard`.

Пример промпта:

> Используй DataLens MCP server. Сначала покажи `dl_runtime_status` и проверь, что все gates изменения выключены. Затем выполни `dl_auth_probe` и перечисли доступные этой учетной записи workbooks. Ничего не сохраняй, не публикуй и не изменяй.

Инструменты возвращают структурированные MCP-результаты и очищают ошибки, связанные с учетными данными. Сервер не должен выводить значения или фрагменты токенов, authorization headers и вычисленные из токена данные.

## Безопасность записи

Обычный сценарий начинается с чтения и планирования. Значение `DATALENS_MCP_ENABLE_WRITES=1` открывает только первый runtime gate и само по себе не разрешает blind write. Для изменения все равно нужны:

1. Известный target и свежий saved readback.
2. Проверенный payload и согласованный safe-apply план.
3. Сохранение revision и технологии объекта.
4. Явное разрешение save и saved readback.
5. Отдельное разрешение publish, если публикация входит в согласованный delivery intent.
6. Published readback и deployment report после публикации.

Инструкции planning, review, draft, save-only и no-publish продолжают блокировать публикацию. QL используется только после прямого запроса QL и никогда не выбирается автоматически. Delete, move и permission operations не входят в обычный write path.

Подробности: [`docs/local-only-safety-model.md`](docs/local-only-safety-model.md), [`docs/safe-apply.md`](docs/safe-apply.md) и [`docs/route-policy.md`](docs/route-policy.md).

## Устройство репозитория

| Путь | Назначение |
| --- | --- |
| `src/datalens_dev_mcp/` | Python package, MCP dispatcher, tools, API client, pipeline, validators и packaged resources |
| `config/` | Версионированные safe defaults, routing policy, style policy и API metadata |
| `schemas/` | JSON Schemas для артефактов проекта и валидации |
| `templates/` | Параметризованные Wizard, Advanced Editor, requirements и project templates |
| `docs/` | Документация оператора, safety, API, tools и workflow |
| `examples/` | Синтетические входные данные, response contracts и конфигурации MCP-клиентов |
| `scripts/` | Offline acceptance, smoke, schema, packaging и maintenance команды |
| `tests/` | Unit и offline integration tests |

Generated outputs, credentials, virtual environments, caches и локальные target-конфиги намеренно исключены из Git. Не коммитьте реальные экспорты объектов и чувствительные operational evidence.

Поток компонентов и trust boundaries описаны в [`docs/architecture.md`](docs/architecture.md). Полная поверхность инструментов — в [`docs/mcp/tools.md`](docs/mcp/tools.md) и [`docs/mcp/response_contracts.md`](docs/mcp/response_contracts.md).

## Локальная конфигурация

Встроенные defaults безопасны для первого запуска. Чтобы задать локальные placeholders или параметры отображения, скопируйте пример в проект дашборда и оставьте копию untracked:

```bash
mkdir -p /absolute/path/to/your/dashboard-project/config
cp config/datalens_mcp.local.example.json \
  /absolute/path/to/your/dashboard-project/config/datalens_mcp.local.json
```

Можно также передать `--local-config /absolute/path/to/config.json` или задать `DATALENS_MCP_LOCAL_CONFIG`. Локальный конфиг не может включить запись или обойти approval, fresh-read, save-first, readback и publish gates. См. [`docs/configuration.md`](docs/configuration.md).

## Разработка

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e .
python3 scripts/run_quick_checks.py
python3 scripts/run_offline_acceptance.py
```

Acceptance suite работает offline и не должен требовать учетных данных. Опциональные live-проверки должны использовать disposable targets и явно включенные gates; см. [`docs/live_testing_local.md`](docs/live_testing_local.md).

Участие в разработке приветствуется. Начните с [`CONTRIBUTING.md`](CONTRIBUTING.md), сообщайте об уязвимостях по правилам [`SECURITY.md`](SECURITY.md) и не размещайте секреты или реальные данные клиентов в issues и pull requests.

## Лицензия и атрибуция

Код проекта и оригинальная документация распространяются по Apache License 2.0; см. [`LICENSE`](LICENSE). Уведомления о стороннем содержимом и условия для справочных данных, полученных из документации, перечислены в [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md).
