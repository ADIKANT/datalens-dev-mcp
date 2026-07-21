# Доступ к DataLens

**Русский** · [English](access_en.md) · [Главная](../README.md) · [Настройка Codex](codex_setup.md)

[Быстрый старт](../README.md#быстрый-старт) · **Доступ к DataLens** · [Подключение](codex_setup.md) · [Инструменты](tools.md) · [Сценарии](usage-flow.md) · [Источники](sources.md) · [Безопасность](local-only-safety-model.md) · [English](access_en.md)

Для работы через Public API нужны Yandex Cloud CLI, ID организации, IAM-токен и права на целевой воркбук. Сервер хранит эти значения в отдельном env-файле и не возвращает их в MCP-ответах.

## 1. Установите и настройте Yandex Cloud CLI

Установите `yc` по [официальной инструкции](https://yandex.cloud/ru/docs/cli/quickstart), затем выполните интерактивную инициализацию:

```bash
yc init
yc config list
```

Команда `yc iam create-token` должна выполняться от того пользователя, которому выдали доступ к DataLens. Если `yc` просит снова войти в систему, завершите интерактивную авторизацию в терминале, затем повторите проверку.

## 2. Получите ID организации

ID можно скопировать в интерфейсе Yandex Cloud или получить способом из инструкции [«Получение ID организации»](https://yandex.cloud/ru/docs/organization/operations/organization-get-id). Это значение будет записано в `DATALENS_ORG_ID`.

Используйте ID той организации, где находятся нужные воркбуки DataLens. У пользователя может быть доступ к нескольким организациям.

## 3. Проверьте роли DataLens

[Роли DataLens](https://yandex.cloud/ru/docs/datalens/security/roles) назначаются на сервис и на конкретные воркбуки или коллекции.

- Для чтения содержимого воркбука подходит `datalens.workbooks.viewer`.
- Для изменения вложенных объектов нужен `datalens.workbooks.editor` или более широкая роль.
- Для публикации вложенных объектов используйте `datalens.workbooks.admin` либо унаследованную роль коллекции с соответствующими правами.

Выдавайте доступ только к тем воркбукам и коллекциям, с которыми будет работать MCP-сервер. Успешная общая проверка API подтверждает чтение списка воркбуков; возможность изменить конкретный объект проверяется по правам на этот объект.

## 4. Создайте IAM-токен

Официальная инструкция: [«Получение IAM-токена для аккаунта локального пользователя»](https://yandex.cloud/ru/docs/iam/operations/iam-token/create-for-local).

```bash
yc iam create-token
```

Токен действует не более 12 часов. Скопируйте результат только в защищённый env-файл. Не вставляйте токен в `config.toml`, аргументы запуска, промпты, логи, issue или файлы репозитория.

## 5. Создайте защищённый env-файл

```bash
mkdir -p ~/.config/datalens-dev-mcp
touch ~/.config/datalens-dev-mcp/env
chmod 600 ~/.config/datalens-dev-mcp/env
```

Заполните `~/.config/datalens-dev-mcp/env`:

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

Передайте MCP-клиенту абсолютный путь к файлу через `DATALENS_ENV_FILE`. [DataLens Public API](https://yandex.cloud/ru/docs/datalens/operations/api-start) использует IAM-токен и ID организации; сервер сам формирует заголовки `Authorization` и `x-dl-org-id`.

### Автоматическое получение и обновление токена

При `DATALENS_ENABLE_TOKEN_REFRESH_ON_401=1` сервер использует настроенную команду `yc iam create-token` в двух случаях:

1. `dl_auth_probe` не нашёл начальный токен в основном env-файле;
2. DataLens вернул HTTP 401 для истёкшего токена.

Полученное значение атомарно записывается в `DATALENS_ENV_FILE`, права файла устанавливаются в `0600`, после чего исходный запрос повторяется один раз. Обновление значения токена в основном env-файле не требует перезапуска клиента: сервер перечитывает файл. Если изменены параметры запуска MCP-процесса, перезапустите клиент.

Если `yc` не находится в `PATH` MCP-процесса, укажите абсолютный путь в `DATALENS_YC_BINARY`. Поле `refresh_available` в ответе `dl_runtime_status` показывает, что команда обновления найдена.

Для ручного режима оставьте автоматическое обновление выключенным и заменяйте `DATALENS_IAM_TOKEN` командой `yc iam create-token` по мере истечения.

## 6. Подключите MCP-клиент

Пример для Codex:

```toml
[mcp_servers.datalens_dev]
command = "/absolute/path/to/datalens-dev-mcp/.venv/bin/datalens-dev-mcp"
args = ["stdio", "--project-root", "/absolute/path/to/your/dashboard-project"]
cwd = "/absolute/path/to/your/dashboard-project"
env = { DATALENS_ENV_FILE = "/absolute/path/to/home/.config/datalens-dev-mcp/env" }
default_tools_approval_mode = "approve"
```

Полная инструкция: [подключение Codex](codex_setup.md). Конфигурации Claude и других клиентов находятся в [`examples/clients/`](../examples/clients/).

## 7. Проверьте настройки и доступ

Сначала вызовите `dl_runtime_status`. Он читает локальную конфигурацию и показывает:

- найден ли основной env-файл;
- заданы ли ID организации и токен;
- доступны ли запись, сохранение и публикация;
- доступно ли обновление токена через `yc`.
- как настроен общий API-limiter и сколько накоплено request, 429, retry и cache-hit событий.

Затем вызовите `dl_auth_probe`. Он выполняет минимальный запрос `getWorkbooksList` с размером страницы 1.

Готовый промпт:

> Вызови `dl_runtime_status` и `dl_auth_probe` через DataLens MCP. Покажи наличие ID организации и токена без их значений, состояние записи, сохранения, публикации и автоматического обновления токена. Затем сообщи результат реальной проверки доступа. Ничего не изменяй.

## Диагностика ошибок доступа

| Результат | Причина | Что сделать |
| --- | --- | --- |
| `missing_credentials` | Не найден ID организации, токен и недоступно получение через `yc` | Проверьте `DATALENS_ENV_FILE`, `DATALENS_ORG_ID`, установку и инициализацию `yc` |
| `expired_token` | Токен истёк, автоматическое обновление отключено или завершилось ошибкой | Выполните `yc iam create-token` и обновите env-файл либо включите обновление на 401 |
| `organization_access_denied` | Пользователь или токен не имеют доступа к указанной организации или объекту | Проверьте ID организации и [роли DataLens](https://yandex.cloud/ru/docs/datalens/security/roles) |
| `yc_reauthentication_required` | Сессия Yandex Cloud CLI требует интерактивного входа | Выполните `yc init` или команду авторизации, предложенную CLI, в терминале |
| `transport_failure` | Недоступен `api.datalens.tech`, нарушен TLS/DNS или мешает proxy | Проверьте сеть, proxy и адрес API |
| `api_failure` | DataLens API вернул техническую ошибку после успешного соединения | Повторите запрос после восстановления сервиса и сохраните очищенный код ответа |

Не публикуйте содержимое env-файла для диагностики. Достаточно результата `dl_runtime_status`, кода категории и очищенного сообщения `dl_auth_probe`.
