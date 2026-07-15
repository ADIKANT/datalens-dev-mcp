# Настройка Codex

**Русский** · [English](codex_setup_en.md) · [Главная](../README.md)

[Быстрый старт](../README.md#быстрый-старт) · [Доступ к DataLens](access.md) · **Подключение** · [Инструменты](tools.md) · [Сценарии](usage-flow.md) · [Источники](sources.md) · [Безопасность](local-only-safety-model.md) · [English](codex_setup_en.md)

Codex запускает `datalens-dev-mcp` как локальный stdio-сервер. Codex app, CLI и расширение IDE используют один формат `config.toml`. Актуальные параметры MCP описаны в [официальной документации Codex](https://learn.chatgpt.com/docs/extend/mcp).

## 1. Установите сервер

```bash
git clone https://github.com/ADIKANT/datalens-dev-mcp.git
cd datalens-dev-mcp
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install .
.venv/bin/datalens-dev-mcp --version
python3 scripts/smoke_mcp_stdio.py
```

Последняя команда проверяет MCP-протокол локально и не обращается к DataLens.

## 2. Подготовьте рабочую папку и доступ

Создайте папку, где сервер сможет хранить планы, снимки и отчёты:

```bash
mkdir -p /absolute/path/to/your/dashboard-project
```

`--project-root` указывает на эту папку. Он не выбирает воркбук или дашборд в DataLens.

Затем выполните инструкцию [«Доступ к DataLens»](access.md): установите `yc`, получите ID организации, проверьте роли и создайте защищённый env-файл.

## 3. Добавьте сервер в `config.toml`

Глобальный файл Codex находится в `~/.codex/config.toml`. Для доверенного проекта можно использовать `.codex/config.toml` в его корне.

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

Используйте абсолютные пути. Параметр `default_tools_approval_mode = "approve"` разрешает обычные вызовы этого сервера без отдельного вопроса Codex перед сохранением или публикацией. Сервер всё равно попросит подтвердить удаление целого объекта DataLens.

Готовый файл: [`examples/clients/codex.toml`](../examples/clients/codex.toml).

## 4. Альтернатива: зарегистрируйте сервер через CLI

```bash
codex mcp add datalens_dev \
  --env DATALENS_ENV_FILE=/absolute/path/to/home/.config/datalens-dev-mcp/env \
  -- /absolute/path/to/datalens-dev-mcp/.venv/bin/datalens-dev-mcp \
  stdio --project-root /absolute/path/to/your/dashboard-project
```

Команда создаёт запись сервера. После неё откройте `~/.codex/config.toml` и добавьте в таблицу `[mcp_servers.datalens_dev]`:

```toml
default_tools_approval_mode = "approve"
startup_timeout_sec = 20
tool_timeout_sec = 120
```

Проверьте регистрацию:

```bash
codex mcp list
```

## 5. Перезапустите Codex

После установки пакета или изменения `config.toml` перезапустите Codex app, CLI-сессию или расширение IDE. В новой задаче откройте `/mcp` и убедитесь, что сервер `datalens_dev` подключён и показывает 38 инструментов.

## 6. Проверьте конфигурацию и доступ

Отправьте промпт:

> Используй DataLens MCP. Вызови `dl_runtime_status` и покажи выбранный project root, версию API, наличие ID организации и токена без их значений, доступность записи, сохранения, публикации и обновления токена. Затем вызови `dl_auth_probe`. На этом шаге ничего не изменяй.

Ожидаемый результат:

- `project_root` совпадает с указанной папкой;
- запись, сохранение и публикация доступны;
- основной env-файл найден;
- `dl_auth_probe` успешно выполняет минимальный `getWorkbooksList`.

Успешная проверка списка воркбуков подтверждает общую авторизацию. Права на конкретный чарт, датасет или дашборд проверяются при чтении и изменении этого объекта.

## 7. Начните работу

Аудит без записи:

> Проведи аудит дашборда `<DASHBOARD_ID>` в воркбуке `<WORKBOOK_ID>`. Прочитай актуальную сохранённую версию, связанные объекты и связи между ними. Покажи найденные проблемы и пути к созданным отчётам. Ничего не сохраняй и не публикуй.

Обычное изменение:

> Исправь `<OBJECT_TYPE>` `<OBJECT_ID>` в воркбуке `<WORKBOOK_ID>`: `<ТРЕБОВАНИЕ>`. Прочитай актуальную сохранённую версию и связи, проверь план и запрос, сохрани изменение, выполни контрольное чтение, опубликуй сохранённую версию и проверь опубликованный результат. Не запрашивай отдельное подтверждение перед сохранением или публикацией.

Дополнительные варианты: [сценарии использования](usage-flow.md).

## 8. Обновление и диагностика

После обновления репозитория переустановите пакет и перезапустите Codex:

```bash
cd /absolute/path/to/datalens-dev-mcp
.venv/bin/python -m pip install .
python3 scripts/smoke_mcp_stdio.py
codex mcp list
```

| Проблема | Проверка |
| --- | --- |
| Сервер не запускается | Выполните `--version`, проверьте абсолютные пути и запустите `scripts/smoke_mcp_stdio.py` |
| В `/mcp` старый список | Переустановите пакет и полностью перезапустите Codex |
| Неверная рабочая папка | Исправьте `args` и `cwd` в `config.toml` |
| Нет доступа к DataLens | Следуйте таблице ошибок в [руководстве по доступу](access.md#диагностика-ошибок-доступа) |
| Codex спрашивает перед каждым инструментом | Проверьте `default_tools_approval_mode = "approve"` внутри таблицы этого сервера и перезапустите Codex |
| Изменение не сохраняется | Проверьте через `dl_runtime_status`, что write и save доступны, затем изучите точную причину блокировки |
| Сохраняется, но не публикуется | Проверьте publish в `dl_runtime_status` и отсутствие `save-only` или `no-publish` в задаче |

Транспортный контракт: [`docs/mcp/local_stdio_contract.md`](mcp/local_stdio_contract.md).
