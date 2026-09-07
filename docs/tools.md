# Инструменты MCP 1.0

**Русский** · [English](tools_en.md) · [Документация](README.md)

Установленный backend публикует закрытую поверхность из 25 прямых инструментов. Точная JSON Schema каждого вызова возвращается через `tools/list`; сервер не принимает произвольный prompt, Python или RPC method.

| Группа | Инструменты |
|---|---|
| Runtime и auth | `dl_server_info`, `dl_auth_check`, `dl_auth_refresh`, `dl_method_schema` |
| Scoped reads | `dl_workbooks_list`, `dl_workbook_entries`, `dl_object_get`, `dl_object_relations`, `dl_dashboard_snapshot` |
| Dataset | `dl_dataset_validate`, `dl_dataset_preview` |
| Authoring | `dl_authoring_defaults`, `dl_compile_recipe`, `dl_editor_validate`, `dl_object_diff` |
| Object lifecycle | `dl_object_create`, `dl_object_update`, `dl_object_publish`, `dl_operation_get`, `dl_operation_reconcile` |
| Maintenance | `dl_backup_export`, `dl_cleanup_preview`, `dl_cleanup_apply`, `dl_admin_inventory`, `dl_admin_assign_licenses` |

Create/update выполняют saved readback; publish отдельно использует свежую saved revision и читает published branch. По умолчанию modifying calls возвращают компактный result, а полный технический record доступен адресно через `dl_operation_get(include_detail=true)`. Dataset preview, provider acceptance и rendered Browser evidence — разные уровни доказательства.
