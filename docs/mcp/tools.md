# Технический каталог MCP

[Пользовательский справочник на русском](../tools.md) · [User guide in English](../tools_en.md) · [Контракты ответов](response_contracts.md)

Источник точной схемы установленной версии — ответ MCP `tools/list`. Стандартная поверхность содержит 38 инструментов. Все аргументы передаются как JSON-объект; неизвестные поля отклоняются схемой инструмента.

## Общие правила

- `project_root` — абсолютный путь к рабочей папке или путь, разрешённый конфигурацией сервера.
- Полные ответы API можно сохранить в project root и вернуть как компактную сводку с `artifact_path`.
- Учётные данные загружаются из `DATALENS_ENV_FILE` и не принимаются как аргументы инструментов.
- Формулировка задачи передаётся в `delivery_intent_text`, когда инструмент должен выбрать read-only, plan-only, save-only или save-and-publish.
- Обычное save/publish не использует отдельные поля подтверждения. Для удаления целого объекта применяется `confirm_delete`.
- Методы записи проверяют write/save/publish непосредственно перед запросом к DataLens.

## Состояние и доступ

### `dl_get_local_config`

- Required: —
- Optional: `config_path`, `project_root`
- Возвращает объединённую local config v2 и источник настроек. Поля с секретами очищаются.

### `dl_runtime_status`

- Required: —
- Optional: `project_root`, `local_config_path`
- Возвращает project root, API-настройки, наличие учётных данных, write/save/publish, `refresh_available` и сведения о загруженной конфигурации.

### `dl_auth_probe`

- Required: —
- Optional: —
- Выполняет `getWorkbooksList(page=1,pageSize=1)`. При настроенном refresh может получить начальный токен или обновить истёкший и повторить запрос один раз.

## Чтение DataLens

### `dl_list_workbooks`

- Required: —
- Optional: `page`, `page_size`
- Возвращает доступные воркбуки в компактном виде.

### `dl_get_workbook_entries`

- Required: `workbook_id`
- Optional: `scope`, `response_mode`, `inline_char_budget`, `project_root`, `run_id`
- Читает объекты воркбука. Большой `full`-ответ сохраняется как artifact.

### `dl_get_entries_relations`

- Required: `entry_ids`
- Optional: —
- Возвращает связи для указанных entry IDs.

### `dl_read_object`

- Required: `object_type`, `object_id`
- Optional: `branch`, `response_mode`, `inline_char_budget`, `project_root`, `run_id`, `workbook_id`
- Выбирает официальный get-метод для dashboard, chart, dataset или connection и возвращает нормализованный результат.

### `dl_snapshot_dashboard`

- Required: `dashboard_id`
- Optional: `project_root`, `workbook_id`, `snapshot_branch`, `include_dormant_summary`, `artifact_retention`
- Читает дашборд и связанные объекты, затем сохраняет manifest и файлы снимка.

## Справка и диагностика

### `dl_validate_editor_runtime_contract`

- Required: один из источников данных Editor
- Optional: `entry`, `sections`, `source`, `allow_unknown_warnings`
- Проверяет структуру Editor, JavaScript и вызовы `Editor.*`.

### `dl_classify_source_error`

- Required: `error_payload`
- Optional: —
- Возвращает категорию, этап и рекомендации для очищенной ошибки источника.

### `dl_diagnose`

- Required: `mode`
- Optional: `payload`, `project_root`, `max_items`
- Анализирует переданные SQL, grain, связи, производительность или оптимизацию. Самостоятельные запросы к источникам данных не выполняет.

### `dl_reference`

- Required: зависит от `mode`
- Optional: `mode`, `query`, `name`, `limit`, `max_chars`, `project_root`
- Возвращает ограниченный набор справочных записей с исходными URL и рекомендацией следующего инструмента.

## Проверка и планирование

### `dl_validate_project`

- Required: —
- Optional: `project_root`, `context_ref`, `evidence_refs`
- Проверяет проектные файлы, маршруты, payload, SQL, связи и секреты.

### `dl_build_payload_plan`

- Required: —
- Optional: `project_root`, `workbook_id`, `delivery_intent_text`, `target_known`, `target_dashboard_id`, `target_chart_id`, `target_url`, `context_ref`, `evidence_refs`
- Компилирует проверенные материалы в список DataLens methods, targets и payload без выполнения записи.

### `dl_build_validation_evidence_report`

- Required: —
- Optional: `project_root`
- Собирает результаты проверок и контрольных чтений в единый отчёт.

### `dl_validate_object`

- Required: `object_type`, `payload`
- Optional: `operation`, `source_adapter`, `execute_validation`
- Проверяет объект по скомпилированной схеме метода и правилам маршрута.

### `dl_plan_object_create`

- Required: `object_type`, `payload`
- Optional: `source_adapter`, `delivery_intent_text`
- Выбирает create-метод, нормализует payload и возвращает план или блокировки.

### `dl_plan_object_update`

- Required: `object_type`, `payload`
- Optional: `mode`, `source_adapter`, `lifecycle_operation`, `delivery_intent_text`
- Строит update поверх актуальной saved-версии с сохранением ID, ревизии, технологии и остальных полей.

### `dl_plan_guarded_dataset_update`

- Required: `dataset_id`, `current_dataset`, `proposed_dataset`
- Optional: `workbook_id`, `affected_chart_payloads`, `validate_only`, `allow_guid_changes`, `execute_validation`, `delivery_intent_text`, `project_root`
- Планирует `getDataset`, `validateDataset`, update и saved readback с проверкой GUID и связанных чартов.

### `dl_plan_dashboard_tab_update`

- Required: `current_dashboard`, `tab`
- Optional: `tab_operation`, `tab_id`
- Возвращает минимальный overlay для добавления или замены одной вкладки.

### `dl_reconcile_partial_creates`

- Required: `workbook_id`, `planned_objects`
- Optional: `entries_payload`
- Сопоставляет план создания с текущими entries и предотвращает дубли после прерванной операции.

### `dl_compile_guarded_rpc_request`

- Required: `method`, `payload`
- Optional: `object_type`, `operation`, `object_id`, `workbook_id`, `mode`, `base_revision`, `fresh_read_artifact_path`, `expected_readback_branch`, `publish_source_artifact`, `changed_sections`
- Создаёт запрос с зафиксированной целью, base revision и ожидаемым branch контрольного чтения.

## Safe Apply

### `dl_create_safe_apply_plan`

- Required: —
- Optional: `project_root`, `readback_mode`, `entries_payload`, `existing_update_actions`, `delivery_intent_text`, `target_known`, `target_dashboard_id`, `target_chart_id`, `target_url`, `context_ref`, `evidence_refs`
- Создаёт plan с режимом задачи, SHA-256 пользовательского запроса, target lock, действиями и блокировками.

### `dl_execute_safe_apply`

- Required: plan, заданный через `plan_path` или найденный в project root по контракту текущей версии
- Optional: `project_root`, `plan_path`, `delivery_intent_text`
- Перечитывает цель, проверяет revision и выполняет save или publish, записанные в plan.

### `dl_create_publish_from_saved_plan`

- Required: `project_root`, `target`, `object_type`
- Optional: `object_id`, `object_ids`, `saved_readback_path`, `readback_mode`, `delivery_intent_text`, `target_dashboard_id`, `target_chart_id`, `target_url`
- Создаёт publish-plan только из saved readback и фиксирует ожидаемые `revId` и `savedId`.

### `dl_readback_and_report`

- Required: цель, достаточная для выбранного object type
- Optional: `project_root`, `target`, `dashboard_id`, `chart_ids`, `dataset_id`, `connection_id`, `branch`, `readback_mode`, `delivery_intent_text`, `target_workbook_id`, `target_url`, `context_ref`, `evidence_refs`
- Читает saved или published состояние и создаёт deployment report.

## Проектный manifest

### `dl_detect_project_live_workflows`

- Required: —
- Optional: `project_root`
- Ищет поддерживаемый manifest и перечисляет объявленные процессы.

### `dl_plan_project_manifest`

- Required: `project_root`
- Optional: `write_manifest`, `overwrite_existing`, `target_workbook_id`, `dashboard_id`
- Возвращает предлагаемый manifest; при `write_manifest=true` записывает его в project root.

### `dl_plan_project_live_workflow`

- Required: `project_root`
- Optional: `workflow_name`, `action`, `publish`, `delivery_intent_text`
- Разбирает действие и возвращает команду, цели, окружение, ожидаемые файлы и блокировки.

### `dl_run_project_live_dry_run`

- Required: `project_root`
- Optional: `workflow_name`, `execute_now`, `timeout_sec`
- Запускает объявленную dry-run-команду и очищает stdout/stderr.

### `dl_run_project_live_apply`

- Required: `project_root`
- Optional: `workflow_name`, `execute_now`, `publish`, `action`, `timeout_sec`, `delivery_intent_text`, `confirm_delete`
- Запускает объявленное apply-действие. `confirm_delete` используется только для удаления целого объекта по совпадающему plan.

### `dl_read_project_live_summary`

- Required: `project_root`
- Optional: `workflow_name`, `action`, `publish`, `summary_path`
- Проверяет JSON summary, цели, количество изменений и полноту результатов.

## Обслуживание и источники

### `dl_run_live_maintenance_update`

- Required: цель и данные, необходимые выбранному режиму
- Optional: project/target IDs, `intent`, `maintenance_mode`, `publish`, baseline, changed objects, source evidence, safe-apply results, saved/published readbacks, UI evidence и target URL
- Координирует точечное изменение и возвращает достигнутый этап. Фактические записи выполняются через Safe Apply.

### `dl_build_dashboard_source_availability_matrix`

- Required: данные хотя бы одного поддерживаемого источника evidence
- Optional: `dashboard_snapshot_path`, inventory/readback/catalog paths, `environments`, `dashboard_object_ids`, `strict_publish_gate`
- Формирует единую матрицу доступности источников.

### `dl_validate_source_availability_consumers`

- Required: данные matrix и consumers
- Optional: `matrix`, `consumers`, `strict_publish_gate`
- Проверяет, что потребители согласованы с состоянием источников.

### `dl_plan_source_availability_patch`

- Required: matrix, достаточная для построения исправления
- Optional: `matrix`, `strict_publish_gate`
- Возвращает план точечной корректировки без обращения к источникам данных.

## Каталог API

### `dl_list_api_methods`

- Required: —
- Optional: `include_guarded_writes`, `limit`
- Возвращает каталог методов, статус поддержки и URL официальной документации.

### `dl_get_api_method_schema`

- Required: `method`
- Optional: —
- Возвращает ограниченную схему request/response, ограничения операции и ссылку на API Reference.

## Выполнение операций

Обычная команда create/fix/update/enhance/redesign проходит `dl_create_safe_apply_plan` → `dl_execute_safe_apply` → saved `dl_readback_and_report` → `dl_create_publish_from_saved_plan` → `dl_execute_safe_apply` → published `dl_readback_and_report`.

Plan-only не вызывает executor. Save-only останавливается после saved readback. Удаление целого объекта требует `confirm_delete=true` для неизменившегося plan с точными IDs.
