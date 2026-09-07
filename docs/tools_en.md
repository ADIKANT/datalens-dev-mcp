# MCP tools 1.0

[Русский](tools.md) · **English** · [Documentation](README_en.md)

The installed backend exposes a closed surface of 25 direct tools. `tools/list` returns the exact JSON Schema for every call; the server accepts no arbitrary prompt, Python, or RPC method.

| Group | Tools |
|---|---|
| Runtime and auth | `dl_server_info`, `dl_auth_check`, `dl_auth_refresh`, `dl_method_schema` |
| Scoped reads | `dl_workbooks_list`, `dl_workbook_entries`, `dl_object_get`, `dl_object_relations`, `dl_dashboard_snapshot` |
| Dataset | `dl_dataset_validate`, `dl_dataset_preview` |
| Authoring | `dl_authoring_defaults`, `dl_compile_recipe`, `dl_editor_validate`, `dl_object_diff` |
| Object lifecycle | `dl_object_create`, `dl_object_update`, `dl_object_publish`, `dl_operation_get`, `dl_operation_reconcile` |
| Maintenance | `dl_backup_export`, `dl_cleanup_preview`, `dl_cleanup_apply`, `dl_admin_inventory`, `dl_admin_assign_licenses` |

Create/update perform saved readback. Publish separately starts from a fresh saved revision and reads the published branch. Modifying calls return compact results by default, while the full technical record is available through `dl_operation_get(include_detail=true)`. Dataset preview, provider acceptance, and rendered Browser evidence are distinct proof levels.
