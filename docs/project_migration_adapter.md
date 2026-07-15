# Подключение существующего проекта

Проект с собственными командами проверки, save и publish подключается через manifest. Сервер не запускает команды, которые в нём не объявлены.

## Последовательность

1. `dl_detect_project_live_workflows` ищет существующий manifest.
2. `dl_plan_project_manifest` показывает предлагаемый файл и записывает его при `write_manifest=true`.
3. Укажите точные `workbook_id`, dashboard/object IDs, argv, summary paths и evidence checks.
4. `dl_plan_project_live_workflow` показывает действие без запуска.
5. `dl_run_project_live_dry_run` выполняет объявленную проверку.
6. `dl_read_project_live_summary` проверяет branch, changed counts, target IDs и evidence paths.
7. При запросе на реализацию `dl_run_project_live_apply` выполняет объявленный save/publish flow.
8. Итоговый summary читается повторно после выполнения.

Начальный manifest может содержать:

```json
{
  "may_execute_command": false,
  "allow_publish": false
}
```

После проверки укажите разрешённые действия явно. Удаление целого объекта использует отдельный action и `confirm_delete`; перемещение и permission changes не добавляются.

Шаблоны находятся в `templates/project_live_workflows/`.
