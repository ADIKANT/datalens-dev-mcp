# MCP tools 1.0

[Русский](tools.md) · **English** · [Documentation](README_en.md)

The installed backend exposes a closed surface of 26 direct tools. `tools/list` returns the exact JSON Schema for every call; the server accepts no arbitrary prompt, Python, or RPC method.

| Group | Tools |
|---|---|
| Runtime and auth | `dl_server_info`, `dl_auth_check`, `dl_auth_refresh`, `dl_method_schema` |
| Scoped reads | `dl_workbooks_list`, `dl_workbook_entries`, `dl_object_get`, `dl_object_relations`, `dl_object_revisions`, `dl_dashboard_snapshot` |
| Dataset | `dl_dataset_validate`, `dl_dataset_preview` |
| Authoring | `dl_authoring_defaults`, `dl_compile_recipe`, `dl_editor_validate`, `dl_object_diff` |
| Object lifecycle | `dl_object_create`, `dl_object_update`, `dl_object_publish`, `dl_operation_get`, `dl_operation_reconcile` |
| Maintenance | `dl_backup_export`, `dl_cleanup_preview`, `dl_cleanup_apply`, `dl_admin_inventory`, `dl_admin_assign_licenses` |

Create/update perform saved readback. Publish separately starts from a fresh saved revision and reads the published branch. Modifying calls return compact results by default, while the full technical record is available through `dl_operation_get(include_detail=true)`. Dataset preview, provider acceptance, and rendered Browser evidence are distinct proof levels.

`dl_object_revisions(entry_id=...)` reads one history page (default 25), preserving provider order, saved/published flags and opaque continuation. It can filter known `rev_ids`; limited history cannot prove a write did not apply.

`dl_dataset_validate(provider=true)` validates current saved state with the provider without saving. Optional `refresh_source_ids` refresh only those source schemas in the returned candidate. Persisting that candidate separately requires `include_provider_state=true`, fresh revisions and an authorized update. Write status and `dataset_validation` are independent.

Errors retain available stage/method/status, safe provider code and Request-ID/Trace-ID. Missing IDs stay null. Error bodies, SQL, login HTML and full SDK exceptions are not exposed; effect certainty and unknown-write replay restrictions remain unchanged.
