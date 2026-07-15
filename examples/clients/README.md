# Примеры MCP-клиентов

[Документация](../../docs/README.md) · [Доступ к DataLens](../../docs/access.md) · [Настройка Codex](../../docs/codex_setup.md)

Все файлы запускают один локальный stdio-процесс. Замените каждый `/absolute/path/...` и передайте абсолютный путь к защищённому `DATALENS_ENV_FILE`.

`--project-root` — локальная папка для входных файлов, снимков, планов и отчётов. Live ID воркбука, дашборда и других объектов передаются в задаче отдельно.

## Codex

Добавьте [`codex.toml`](codex.toml) в `~/.codex/config.toml` или объедините блок сервера с существующим файлом. Параметр `default_tools_approval_mode = "approve"` нужен, чтобы Codex не задавал отдельный вопрос перед обычным save/publish.

CLI-регистрация:

```bash
codex mcp add datalens_dev \
  --env DATALENS_ENV_FILE=/absolute/path/to/home/.config/datalens-dev-mcp/env \
  -- /absolute/path/to/datalens-dev-mcp/.venv/bin/datalens-dev-mcp \
  stdio --project-root /absolute/path/to/your/dashboard-project
```

После команды откройте созданный блок `[mcp_servers.datalens_dev]` и добавьте:

```toml
default_tools_approval_mode = "approve"
```

Перезапустите Codex, проверьте `codex mcp list` и `/mcp`.

## Claude Code

```bash
claude mcp add --transport stdio --scope local \
  --env DATALENS_ENV_FILE=/absolute/path/to/home/.config/datalens-dev-mcp/env \
  datalens-dev -- \
  /absolute/path/to/datalens-dev-mcp/.venv/bin/datalens-dev-mcp \
  stdio --project-root /absolute/path/to/your/dashboard-project
```

Проверьте `claude mcp list`.

## Claude Desktop

Добавьте объект из [`claude-desktop.json`](claude-desktop.json) в `claude_desktop_config.json` и перезапустите приложение.

## Другие клиенты

[`generic-stdio.json`](generic-stdio.json) содержит отдельные `command`, `args` и `env`. Это описание локального процесса, а не HTTP endpoint.

## Первая проверка

> Вызови `dl_runtime_status` и `dl_auth_probe` через DataLens MCP. Покажи доступность write/save/publish и результат авторизации без значений учётных данных. На этом шаге ничего не изменяй.

Стандартный env-файл включает write/save/publish. Формулировка задачи определяет операцию: аудит не пишет, plan-only только планирует, save-only не публикует, а явное изменение проходит save и publish. Удаление целого объекта подтверждается отдельно.
