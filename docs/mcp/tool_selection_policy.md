# Выбор инструментов

Стандартный `tools/list` содержит 39 инструментов. Выбор начинается с цели пользователя, а не с имени низкоуровневого метода.

## Рекомендуемый порядок

1. `dl_runtime_status` и `dl_auth_probe` — конфигурация и доступ.
2. `dl_list_workbooks`, `dl_get_workbook_entries`, `dl_snapshot_dashboard`, `dl_read_object`, `dl_get_entries_relations` — актуальное состояние.
3. `dl_reference` и `dl_diagnose` — справка и диагностика при необходимости.
4. `dl_plan_object_create` или `dl_plan_object_update` — обычный жизненный цикл объекта.
5. `dl_plan_guarded_dataset_update` или `dl_plan_dashboard_tab_update` — специализированные изменения.
6. `dl_validate_object`, `dl_validate_editor_runtime_contract`, `dl_validate_project` — проверки.
7. `dl_build_payload_plan` и `dl_create_safe_apply_plan` — план применения.
8. `dl_execute_safe_apply` — только когда режим задачи требует save или publish.
9. `dl_readback_and_report` — контрольное чтение каждого выполненного этапа.
10. `dl_create_publish_from_saved_plan` — публикация из verified saved state.

Используйте `dl_list_api_methods` и `dl_get_api_method_schema`, чтобы уточнить контракт официального метода. Для вызова записи всё равно применяется общий object plan и Safe Apply.

Произвольное удаление целого объекта недоступно. Manifest action
`retire_legacy_objects` требует `confirm_delete=true` для совпадающего плана.
Удаление содержимого внутри объекта остаётся update.
