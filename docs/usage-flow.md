# Прямые операции DataLens

[English](usage-flow_en.md) · [Подключение](codex_setup.md) · [25 инструментов](tools.md) · [Документация](README.md)

Работайте из точного dashboard project/subproject через установленные domain skills. Текущий backend предоставляет прямые типизированные операции. Модель выбирает нужный skill и вызывает его инструменты; точные schemas аргументов возвращает установленный `tools/list`.

## Чтение и выбор

Начинайте с указанного URL или точного объекта. Используйте `dl_server_info` для версии runtime и `dl_auth_check`, когда нужна безопасная проверка доступа. Читайте объект через `dl_object_get`, явно выбирая saved или published branch, а нужные зависимости — через `dl_object_relations`. `dl_workbooks_list` и `dl_workbook_entries` нужны для inventory; проходите страницы и явно отмечайте неполноту.

Read-only анализ завершается отчётом без mutation и создания файлов проекта. Target и visual reference — разные объекты. Сохраняйте текущую технологию, ручную геометрию и изменения за пределами поручения.

## Authoring и доставка

Выберите [Dataset/Wizard](../skills/datalens-dataset-wizard/SKILL.md), [Editor](../skills/datalens-editor/SKILL.md) или [Dashboard](../skills/datalens-dashboard/SKILL.md). Для нового стандартного чарта предпочтителен Wizard; существующий Editor или Wizard сохраняет технологию. QL требует прямого запроса.

Используйте реальные Dataset GUID и применимые проверки `dl_dataset_validate` / `dl_dataset_preview`. Для зарегистрированного recipe вызовите `dl_authoring_defaults`, затем `dl_compile_recipe` с typed bindings и presentation. Приоритет defaults: generic → user → project → explicit reference → explicit call. Передавайте компактный `draft_reference` в validation/create; для update используйте его artifact path с точным target и свежей revision. Не переписывайте и не возвращайте целиком packaged renderer.

Проверьте draft batch через `dl_editor_validate`; используйте `dl_object_diff`, если нужно сравнение точечного изменения. Создавайте зависимости по порядку через `dl_object_create` либо обновляйте целевой объект через `dl_object_update`. Оба выполняют saved readback. Когда публикация запрошена и поддержана для этого типа объекта, вызовите `dl_object_publish` из свежей saved revision и проверьте published readback. Dataset и Connection не получают выдуманный publish lifecycle.

При размещении нового recipe chart передавайте compiled `visual_contract` в dashboard item `presentation`. Сохраняйте явно выбранного owner title/hint и ручной layout. Для семантики KPI, времени, шкал и принятой композиции читайте только нужные разделы [visualization decisions](../skills/datalens-dashboard/references/decision-quality.md).

Однозначное поручение разрешает предусмотренную доставку без повторных вопросов plan/save/publish. Краткий план информирует пользователя. Read-only запрещает запись; save-only заканчивается saved readback. Уточнение требуется только при неразрешённом конфликте target/scope или реальной границе доступа. Пример:

> Обнови этот chart, сохрани соседние widgets, сохрани и опубликуй изменение, проверь результат.

## Проверка и reconciliation

Разделяйте Dataset query result, provider acceptance, saved/published identity и реальное отображение. Browser применяется read-only, когда требуется rendered evidence, после API/readback и применимых data checks. Offline validator или наличие настройки не доказывают отображение.

Записи возвращают компактные operation results. Используйте `dl_operation_get` для деталей и `dl_operation_reconcile` при неопределённом результате. Потеря ответа не разрешает слепой повтор записи.

## Backup и scoped cleanup

Используйте [Maintenance](../skills/datalens-maintenance/SKILL.md). `dl_backup_export` экспортирует snapshots и не заявляет проверенный full restore. Для порученного cleanup `dl_cleanup_preview` получает dependency/preservation evidence; `dl_cleanup_apply` принимает неизменённый точный `confirmed_delete` и заново проверяет scope перед записью. Однозначный запрос на эти удаления уже является разрешением; машинный scope не означает новую реплику человека. Изменившийся preview сверяется с запросом; конфликт сохранности соседей или расширение scope требуют остановки. Failed/uncertain deletion останавливает оставшиеся объекты.

Запрос только показать список не разрешает удаление. Сохраняйте явно оставленные объекты. Dashboard-задача не разрешает ACL changes, upstream production database writes или чужие объекты. См. [границы поручения и доставки](../skills/datalens-dashboard/references/authorized-scope.md).
