# Подключение DataLens к Codex

[English](codex_setup_en.md) · [Установка](installation.md) · [Использование](usage-flow.md)

Требуется Python 3.11+. Установите backend в устойчивое окружение. Из checkout репозитория:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install .
.venv/bin/datalens-dev-mcp --version
.venv/bin/python scripts/installed_smoke.py
```

Smoke проверяет импорт из `site-packages` без `PYTHONPATH`, совпадение версии, инициализацию stdio и закрытый набор из 25 инструментов из временной папки. Это offline-доказательство установки, а не проверка live-доступа или отображения.

Установите или включите repository plugin поддержанным способом клиента. Его [manifest](../.codex-plugin/plugin.json) подключает пять domain skills и [.mcp.json](../.mcp.json). Bundled stdio-конфигурация:

```json
{
  "mcpServers": {
    "datalens": {
      "command": "datalens-dev-mcp",
      "args": ["stdio"]
    }
  }
}
```

Установленный executable должен быть доступен в `PATH` MCP-процесса. При ручной регистрации stdio укажите абсолютный путь установленного executable и единственный аргумент `stdio`. Ручная регистрация сервера сама по себе не устанавливает domain skills. Сохраните одну выбранную регистрацию, чтобы не вызвать старый backend.

Для live-доступа задайте `DATALENS_ORG_ID` и `DATALENS_IAM_TOKEN` в окружении процесса либо защищённом файле `${XDG_CONFIG_HOME:-~/.config}/datalens-dev-mcp/credentials.env`. Явный `DATALENS_ENV_FILE` имеет приоритет. Сохраните существующие credentials; не вставляйте их значения в prompts и диагностику.

После обновления backend и plugin snapshot откройте новую обычную задачу из точного dashboard project/subproject. Проверьте runtime через `dl_server_info`, прочитайте schemas его `tools/list` и используйте `dl_auth_check` для безопасной проверки live-доступа. Версия runtime, успешная авторизация, права на конкретный объект и отображение — отдельные проверки.

Однозначный scoped запрос разрешает предусмотренные save/readback и publish/readback. Краткий план не добавляет approval-паузу; ограничения read-only и save-only обязательны. Реальные native permissions остаются под управлением клиента. Автоматический allow не означает ожидание человека; не меняйте глобальные approvals и внешние skills для обхода ограничения. См. [границы поручения](../skills/datalens-dashboard/references/authorized-scope.md).

При ошибке запуска проверьте путь executable и окружение процесса. При неудачном live probe укажите конкретную границу авторизации или доступа без credentials. Если runtime показывает другой набор инструментов, устраните несовпадение backend/plugin до записи. Используйте [текущие инструменты](tools.md) и [предметный маршрут](usage-flow.md), получая точные аргументы из установленной schema.
