# Проверка проекта

## Offline acceptance

Основная проверка не обращается к DataLens и не требует учётных данных:

```bash
python3 scripts/run_offline_acceptance.py
```

Она проверяет Python-код, MCP-протокол, схемы, 38 инструментов, пакетные ресурсы, документацию, секреты и сборку wheel.

Для быстрого локального цикла:

```bash
python3 scripts/run_quick_checks.py
python3 scripts/smoke_mcp_stdio.py
python3 scripts/run_server_efficiency_suite.py --strict
```

Последняя команда проверяет детерминированные бюджеты самого сервера: общий
интервал 1,05 секунды и эффективную частоту 57,14 старта/мин, reuse
runtime-manifest, revision-aware snapshot, кэши project/Editor validation,
15-КБ проекцию тяжёлых ответов и отсутствие дублирования delivery-блоков.
Масштабированный синтетический сценарий с логической задержкой чтения 1,5
секунды сравнивает serial и трёхпоточный snapshot, требует ускорение не менее
25% и одинаковый SHA compact graph. Live-записи не выполняются.

## Installed stdio smoke

Соберите wheel, установите его во временное окружение и запустите stdio smoke. Это подтверждает, что пакет использует включённые assets и не зависит от текущей рабочей папки.

## Live read

Live read проверяет авторизацию, список воркбуков и чтение выбранного объекта. Используйте внешний `DATALENS_ENV_FILE`; реальные токены и ответы объектов не добавляются в тестовые артефакты.

## Live save and publish

Проверки записи выполняются на специально выбранных объектах. Запрос save-only должен завершиться saved readback без publish. Запрос на реализацию должен пройти save, saved readback, publish-from-saved и published readback. Для видимого изменения добавьте проверку DataLens.

## Delete

Проверка удаления использует только manifest action `retire_legacy_objects`,
отдельный тестовый объект и двухшаговый `confirm_delete` flow. Цель и hash
плана должны совпадать; после выполнения требуется чтение, подтверждающее
отсутствие объекта.

## Перед коммитом

```bash
python3 scripts/run_offline_acceptance.py
python3 scripts/check_public_release.py
git diff --check
```

Live-проверки не входят в обязательный offline gate.
