# Инструменты MCP 1.0

**Русский** · [English](tools_en.md) · [Документация](README.md)

Установленный backend публикует закрытую поверхность из 26 прямых инструментов. Точная JSON Schema каждого вызова возвращается через `tools/list`; сервер не принимает произвольный prompt, Python или RPC method.

| Группа | Инструменты |
|---|---|
| Runtime и auth | `dl_server_info`, `dl_auth_check`, `dl_auth_refresh`, `dl_method_schema` |
| Scoped reads | `dl_workbooks_list`, `dl_workbook_entries`, `dl_object_get`, `dl_object_relations`, `dl_object_revisions`, `dl_dashboard_snapshot` |
| Dataset | `dl_dataset_validate`, `dl_dataset_preview` |
| Authoring | `dl_authoring_defaults`, `dl_compile_recipe`, `dl_editor_validate`, `dl_object_diff` |
| Object lifecycle | `dl_object_create`, `dl_object_update`, `dl_object_publish`, `dl_operation_get`, `dl_operation_reconcile` |
| Maintenance | `dl_backup_export`, `dl_cleanup_preview`, `dl_cleanup_apply`, `dl_admin_inventory`, `dl_admin_assign_licenses` |

Create/update выполняют saved readback; publish отдельно использует свежую saved revision и читает published branch. По умолчанию modifying calls возвращают компактный result, а полный технический record доступен адресно через `dl_operation_get(include_detail=true)`. Dataset preview, provider acceptance и rendered Browser evidence — разные уровни доказательства.

`dl_object_revisions(entry_id=...)` читает одну страницу истории (по умолчанию 25), сохраняя порядок провайдера, saved/published flags и opaque continuation. Допустим фильтр по известным `rev_ids`; неполная история не доказывает неприменение записи.

`dl_dataset_validate(provider=true)` проверяет текущее сохранённое состояние у провайдера без записи. `refresh_source_ids` обновляет схему только указанных источников в возвращённом кандидате; для его отдельного сохранения нужен полный результат с `include_provider_state=true`, свежие ревизии и разрешённый update. Статус сохранения и `dataset_validation` независимы.

Ошибки сохраняют доступные stage/method/status, безопасный provider code и Request-ID/Trace-ID. Отсутствующий ID не подменяется вымышленным. Тела ошибок, SQL, HTML login и полные SDK exceptions не выводятся; certainty и запрет retry неизвестных записей сохраняются.
