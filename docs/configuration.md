# Локальная конфигурация

**Русский** · [English](configuration_en.md) · [Доступ к DataLens](access.md) · [Безопасность](local-only-safety-model.md)

## Порядок загрузки

Сервер ищет локальную конфигурацию в следующем порядке:

1. путь из `--local-config`;
2. путь из `DATALENS_MCP_LOCAL_CONFIG`;
3. `config/datalens_mcp.local.json` в корне репозитория;
4. настройки, встроенные в пакет.

Файл `config/datalens_mcp.local.json` исключён из Git. Начните с примера:

```bash
cp config/datalens_mcp.local.example.json config/datalens_mcp.local.json
python3 scripts/validate_schemas.py
python3 scripts/smoke_mcp_stdio.py
```

## Режим выполнения

Local config v2 содержит раздел:

```json
{
  "execution": {
    "default": "follow_user_request",
    "writes": true,
    "save": true,
    "publish": true,
    "delete_requires_confirmation": true
  }
}
```

`follow_user_request` выбирает действие по формулировке задачи:

- аудит, проверка и диагностика работают только на чтение;
- `plan-only` создаёт план;
- `save-only` и `no-publish` сохраняют без публикации;
- создание, исправление, обновление и переработка проходят через save и publish;
- project manifest action `retire_legacy_objects` требует
  `confirm_delete=true` для неизменившегося плана; произвольное удаление
  целого объекта недоступно.

Конфигурация старого формата автоматически приводится к v2 при загрузке. Итоговые настройки можно проверить через `dl_get_local_config`.

## Основной env-файл

Учётные данные и жёсткие выключатели хранятся вне репозитория:

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
# DATALENS_YC_BINARY=/absolute/path/to/yc
```

Передайте абсолютный путь к файлу в `DATALENS_ENV_FILE`. Основной env-файл перечитывается при проверке доступа и перед операциями записи. Для write/save/publish значение `0` в файле или в окружении процесса всегда имеет приоритет над значением `1`.

Если `yc` отсутствует в `PATH` MCP-процесса, задайте `DATALENS_YC_BINARY`. `dl_runtime_status` показывает `refresh_available`, не раскрывая путь к токену или его значение.

## Жёсткие выключатели

Значение `0` в основном env-файле или в окружении MCP-процесса всегда запрещает соответствующее действие:

| Переменная | Результат при `0` |
| --- | --- |
| `DATALENS_MCP_ENABLE_WRITES` | Все запросы записи блокируются |
| `DATALENS_MCP_LIVE_ALLOW_SAVE` | Save-запросы блокируются |
| `DATALENS_MCP_LIVE_ALLOW_PUBLISH` | Разрешённое сохранение завершается состоянием `saved_not_published` |
| `DATALENS_ENABLE_TOKEN_REFRESH_ON_401` | Токен обновляется пользователем вручную |

Изменения write/save/publish и IAM-токена в основном env-файле применяются перед следующим RPC без перезапуска. Для изменения переменной, заданной непосредственно при запуске процесса, перезапустите MCP-клиент.

## Разделы конфигурации

- `defaults` — рабочая папка и необязательные ID проекта, воркбука и дашборда;
- `execution` — режим по запросу пользователя и доступность write/save/publish;
- `safe_apply` — актуальное чтение, сохранение ревизии, save-first и контрольное чтение;
- `readback` — объём контрольного чтения;
- `validation` — строгость, проверка маршрута, связей, шаблонов и секретов;
- `live_testing` — запуск проверок на специально выбранных объектах;
- `api_defaults` — интервалы, повторные попытки и timeout;
- `routing` — выбор Wizard, Editor и QL;
- `style`, `naming`, `selectors` — оформление и компоновка объектов.

## Проверка итоговой конфигурации

Вызовите:

```json
{"name": "dl_get_local_config", "arguments": {}}
```

Ответ содержит объединённые настройки и источник файла. Поля с именами token, authorization, password и secret очищаются рекурсивно.

Затем используйте `dl_runtime_status`, чтобы проверить реальные возможности процесса. Полный путь настройки доступа приведён в [`access.md`](access.md).
