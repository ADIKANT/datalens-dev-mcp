# Работа с проектной папкой

[Сценарии](usage-flow.md) · [Инструменты](tools.md) · [Safe Apply](safe-apply.md)

`--project-root` задаёт папку для требований, снимков, планов, проверок и отчётов. Live-объект DataLens определяется отдельным типом и ID.

## Обычный проект

1. Проверить настройки и доступ через `dl_runtime_status` и `dl_auth_probe`.
2. Найти воркбук и прочитать целевой объект, его связи и актуальную saved-версию.
3. Построить create/update план и проверить объект.
4. Запустить проектную валидацию и собрать payload plan.
5. Создать Safe Apply plan с режимом исходной задачи и target lock.
6. Для plan-only остановиться; для save-only сохранить и прочитать saved-версию.
7. Для create/fix/update/enhance/redesign сохранить, проверить saved-версию, опубликовать из неё и проверить published-версию.
8. Для видимого изменения проверить изменённую область в интерфейсе DataLens.

## Проект с manifest

Проект может объявить собственные команды dry-run, save и publish в `.datalens-mcp.json`, `datalens-mcp.project.json`, `.datalens-mcp.yaml` или `.datalens-mcp.yml`.

1. `dl_detect_project_live_workflows` находит manifest.
2. `dl_plan_project_manifest` показывает предлагаемый файл и записывает его при `write_manifest=true`.
3. `dl_plan_project_live_workflow` возвращает точную команду, цели, окружение и ожидаемые отчёты.
4. `dl_run_project_live_dry_run` запускает объявленную проверку.
5. `dl_read_project_live_summary` проверяет JSON-отчёт и полноту результатов.
6. `dl_run_project_live_apply` запускает объявленное действие, когда режим задачи требует записи.
7. Итоговый summary читается повторно после выполнения.

Manifest должен содержать точные команды, идентификаторы целей, допустимые имена переменных окружения, ожидаемые файлы и проверки. Произвольные команды через этот механизм не запускаются.

Для проекта с единым JS-стилем manifest может дополнительно объявить
`"authoring_profile": {"id": "standard_editor_v1"}`. Тогда
`dl_generate_editor_bundle` выбирает шаблон семейства из стандартного реестра,
сверяет SHA-256 всего набора assets и результата и блокирует несовместимый route,
изменившийся набор или незарегистрированное семейство. Повторный вызов использует
кэшированный fingerprint неизменившихся пакетных ресурсов.

Проект может зарегистрировать собственный профиль без изменения пакета:

```json
{
  "authoring_profile": {
    "id": "project_style_v1",
    "descriptor_path": "profiles/project_style_v1/profile.json",
    "descriptor_sha256": "<SHA256>"
  }
}
```

Descriptor и каждый объявленный asset должны находиться внутри project root.
Сервер проверяет SHA-256 descriptor, fingerprint полного template set,
поддержанные Editor routes и `fallback_policy=block`. Path escape, symlink
escape, изменившийся asset или незарегистрированное семейство блокируют
генерацию.

Все project-live команды запускаются durable worker-процессом. Параметр
`wait_for_completion_sec` (`0..30`, по умолчанию `5`) задаёт только время
ожидания ответа MCP: незавершённая команда возвращает `status=running`,
`execution_id`, heartbeat и deadline. Повторный эквивалентный запуск
присоединяется к тому же execution key; вызов с `execution_id` только читает
состояние. После перезапуска MCP polling продолжается по атомарным state/result
files и никогда не перезапускает исходную команду.

## Пользовательские решения

`dl_update_user_decision` по-прежнему сохраняет читаемое решение в
`requirements/user_decisions.md`. Необязательный `decision_patch` добавляет
машиночитаемую запись в `requirements/user_decisions.v2.json` со scope
`project`, `family` или `object`, изменениями metric semantics/Visual Spec,
семантическими ролями и `supersedes`.

Активные решения применяются детерминированно в порядке
project → family → object. Генерация записывает hash ledger в chart decision,
валидация выявляет drift, а Safe Apply блокирует план, созданный до последней
коррекции.

## Удаление

Произвольное удаление целого объекта не поддерживается. Только объявленное
действие `retire_legacy_objects` требует отдельного подтверждения точного плана
с ID и связями. Удаление элемента внутри дашборда, чарта или датасета проходит
как update. Перемещение и изменение прав доступа не поддерживаются.

## Итоговый отчёт

После выполнения отдельно фиксируются saved readback, published readback и проверка интерфейса. Статическая валидация подтверждает форму запроса, API-readback — структуру объекта, проверка DataLens — отображение.
