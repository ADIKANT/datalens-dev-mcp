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
- `tools/list` по умолчанию возвращает 8 инструментов `autonomous-v2` с
  `name`, `description`, `inputSchema` и `outputSchema`; избыточный `title` не передаётся.
- `tools/call` возвращает одинаковые JSON text и `structuredContent` вместе с `isError`; прикладная ошибка кодируется как JSON с `ok: false`.

Runtime следует пользовательскому запросу через task contract. Write/save/publish доступны, а audit/plan-only не выполняют запись. Save-only останавливается после saved readback. Существенная mutation требует одного подтверждения компактного immutable плана; неизменённые save и publish второго вопроса не создают. Destructive cleanup ограничен точными run-owned объектами с ownership receipt и task-bound token.

## Локальная проверка

```bash
python3 scripts/smoke_mcp_stdio.py
```

Smoke запускает сервер subprocess, проверяет initialize, tools, prompts, resources, ошибочный метод и malformed JSON. Любая строка stdout, которая не является JSON-RPC, завершает проверку ошибкой.
