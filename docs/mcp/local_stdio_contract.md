# Локальный stdio-контракт MCP

`datalens-dev-mcp` запускается MCP-клиентом как локальный subprocess. Сервер не открывает HTTP/SSE listener.

## Конфигурация Codex

```toml
[mcp_servers.datalens_dev]
command = "/absolute/path/to/datalens-dev-mcp/.venv/bin/datalens-dev-mcp"
args = ["stdio", "--project-root", "/absolute/path/to/project"]
cwd = "/absolute/path/to/project"
env = { DATALENS_ENV_FILE = "/absolute/path/to/home/.config/datalens-dev-mcp/env" }
default_tools_approval_mode = "approve"
```

Полная инструкция: [`docs/codex_setup.md`](../codex_setup.md).

## Правила stdio

- `stdin` принимает MCP JSON-RPC сообщения.
- `stdout` содержит только MCP JSON-RPC ответы.
- Логи, диагностические сведения и traceback пишутся в `stderr`.
- `initialize` возвращает версию протокола, capabilities и server info.
- `notifications/initialized` не создаёт ответ в stdout.
- `tools/list` возвращает 38 инструментов с `name`, `description` и
  `inputSchema`; избыточный `title` не передаётся.
- `tools/call` возвращает MCP content и `isError`; прикладная ошибка кодируется как JSON с `ok: false`.

Стандартный runtime следует пользовательскому запросу. Write/save/publish доступны, а audit/plan-only не выполняют запись. Save-only останавливается после saved readback. Обычная команда на изменение проходит save и publish без повторного подтверждения. Произвольное удаление целого объекта недоступно; manifest action `retire_legacy_objects` требует `confirm_delete`.

## Локальная проверка

```bash
python3 scripts/smoke_mcp_stdio.py
```

Smoke запускает сервер subprocess, проверяет initialize, tools, prompts, resources, ошибочный метод и malformed JSON. Любая строка stdout, которая не является JSON-RPC, завершает проверку ошибкой.
