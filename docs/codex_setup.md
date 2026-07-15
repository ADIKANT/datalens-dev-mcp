# Настройка Codex

**Русский** · [English](codex_setup_en.md) · [Документация](README.md) · [Полный Flow](usage-flow.md)

Codex запускает `datalens-dev-mcp` как локальный stdio MCP server. Codex app, CLI и IDE extension используют одну конфигурацию на одном host. Официальная справка: [Model Context Protocol in Codex](https://learn.chatgpt.com/docs/extend/mcp).

## 1. Установите сервер

Требуется Python 3.11 или новее:

```bash
git clone https://github.com/ADIKANT/datalens-dev-mcp.git
cd datalens-dev-mcp
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install .
.venv/bin/datalens-dev-mcp --version
python3 scripts/smoke_mcp_stdio.py
```

Smoke test работает offline, проверяет MCP initialization/tools/prompts/resources и не обращается к DataLens.

## 2. Выберите project root

```bash
mkdir -p /absolute/path/to/your/dashboard-project
```

`--project-root` определяет локальную директорию для requirements, plans, validation outputs и deployment artifacts. Он не выбирает live workbook или dashboard; object IDs передаются tools отдельно.

Read-only относится к DataLens mutations. Локальные planners могут записывать artifacts внутрь project root.

## 3. Создайте внешний env-файл

Offline tools работают без credentials. Для live reads:

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

DATALENS_MCP_ENABLE_WRITES=0
DATALENS_MCP_LIVE_ALLOW_SAVE=0
DATALENS_MCP_LIVE_ALLOW_PUBLISH=0
DATALENS_MCP_ENABLE_EXPERT_RPC=0
```

`YC_IAM_TOKEN` может заменить `DATALENS_IAM_TOKEN`. Храните файл вне checkout и передавайте Codex только абсолютный путь.

## 4. Зарегистрируйте MCP server

### В Codex app

1. Откройте **Settings** → **MCP servers**.
2. Нажмите **Add server**.
3. Выберите **STDIO** и задайте command/arguments из примера ниже.
4. Сохраните server и нажмите **Restart**.

### Через `config.toml`

Глобальная конфигурация находится в `~/.codex/config.toml`. Для trusted project можно использовать `.codex/config.toml` в project root.

```toml
[mcp_servers.datalens_dev]
command = "/absolute/path/to/datalens-dev-mcp/.venv/bin/datalens-dev-mcp"
args = ["stdio", "--project-root", "/absolute/path/to/your/dashboard-project"]
cwd = "/absolute/path/to/your/dashboard-project"
env = { DATALENS_ENV_FILE = "/absolute/path/to/home/.config/datalens-dev-mcp/env" }
startup_timeout_sec = 20
tool_timeout_sec = 120
```

Готовый шаблон: [`examples/clients/codex.toml`](../examples/clients/codex.toml).

### Через CLI

```bash
codex mcp add datalens-dev \
  --env DATALENS_ENV_FILE=/absolute/path/to/home/.config/datalens-dev-mcp/env \
  -- /absolute/path/to/datalens-dev-mcp/.venv/bin/datalens-dev-mcp \
  stdio --project-root /absolute/path/to/your/dashboard-project
```

Проверьте регистрацию:

```bash
codex mcp list
codex mcp --help
```

После добавления или изменения server перезапустите Codex. В interactive composer используйте `/mcp`, чтобы увидеть активные servers и tools.

## 5. Проверьте безопасный runtime

Prompt:

> Вызови `dl_runtime_status` через DataLens MCP. Покажи project root, API version, auth presence и mutation gates. Убедись, что `allow_writes`, `allow_save`, `allow_publish` и `expert_rpc_enabled` выключены. Не вызывай mutation tools.

Проверьте:

- reported project root совпадает с выбранным;
- `allow_writes`, `allow_save`, `allow_publish` равны `false`;
- `expert_rpc_enabled` равен `false`;
- credential presence показан без значения, prefix или length токена;
- standard tool surface содержит 38 tools.

## 6. Проверьте live read

Prompt:

> Выполни `dl_auth_probe`, затем `dl_list_workbooks`. Это read-only проверка. Ничего не сохраняй, не публикуй и не изменяй.

`dl_auth_probe` выполняет минимальный `getWorkbooksList`. При `BLOCKED_LIVE_CREDENTIALS` исправьте внешний env-файл и перезапустите MCP process. Не передавайте token в chat для диагностики.

После успешного probe используйте `dl_get_workbook_entries`, `dl_snapshot_dashboard`, `dl_read_object` и `dl_get_entries_relations`.

## 7. Начните реальную работу

Для существующего dashboard рекомендуемый Codex Flow:

1. runtime/auth preflight;
2. workbook inventory;
3. fresh dashboard snapshot и relation graph;
4. object/route/API planning;
5. object и project validation;
6. payload и unapproved safe-apply plan;
7. guarded save при approval и включенных gates;
8. saved readback;
9. publish-from-saved только когда delivery intent разрешает;
10. published readback и browser/runtime QA.

Готовые prompts для read-only, plan-only, save-only и publish: [Flow использования](usage-flow.md).

## 8. Обновление и удаление регистрации

После обновления checkout переустановите package и перезапустите Codex:

```bash
cd /absolute/path/to/datalens-dev-mcp
.venv/bin/python -m pip install .
python3 scripts/smoke_mcp_stdio.py
codex mcp list
```

Для удаления или других management actions используйте команды из `codex mcp --help`. Source of truth — выбранный global или project `config.toml`.

## Troubleshooting

- **Server не стартует:** проверьте executable `--version`, абсолютные paths и `python3 scripts/smoke_mcp_stdio.py`.
- **Codex показывает старый tools list:** переустановите package и выполните restart app/extension.
- **Неверный project root:** исправьте `args` и `cwd`, затем restart.
- **Auth перестал работать:** IAM token мог истечь; обновите только внешний env-файл и restart process.
- **Unexpected write block:** сначала проверьте, что block корректен; write/save/publish, approval, fresh read и readback — независимые gates.
- **Protocol parse error/stdout pollution:** запустите smoke test; stdout зарезервирован для MCP JSON-RPC, diagnostics должны идти в stderr.

Краткий технический reference: [`docs/mcp/codex_connection.md`](mcp/codex_connection.md). Transport contract: [`docs/mcp/local_stdio_contract.md`](mcp/local_stdio_contract.md).
