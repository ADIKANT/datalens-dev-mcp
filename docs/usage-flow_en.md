# Direct DataLens operations

[Русский](usage-flow.md) · [Connect](codex_setup_en.md) · [25 tools](tools_en.md) · [Documentation](README_en.md)

Work from the exact dashboard project or subproject using the installed domain skills. The current backend exposes direct typed operations. The model selects the relevant skill and calls its tools; the installed `tools/list` supplies exact argument schemas.

## Inspect and choose

Start from the requested URL or exact object identity. Use `dl_server_info` for runtime identity and `dl_auth_check` when a harmless access probe is needed. Read the object with `dl_object_get`, selecting saved or published branch explicitly, and required dependencies with `dl_object_relations`. Use `dl_workbooks_list` and `dl_workbook_entries` only when inventory is needed; paginate and report incomplete results honestly.

For read-only analysis, report findings without mutation or project-file creation. Target and visual reference are separate objects. Preserve the current technology, manual geometry and edits outside the request.

## Author and deliver

Choose [Dataset/Wizard](../skills/datalens-dataset-wizard/SKILL.md), [Editor](../skills/datalens-editor/SKILL.md), or [Dashboard](../skills/datalens-dashboard/SKILL.md). Prefer Wizard for a new standard chart; preserve an existing Editor or Wizard technology. QL requires a direct request.

Use real Dataset field GUIDs and applicable `dl_dataset_validate` / `dl_dataset_preview` checks. For a registered recipe, call `dl_authoring_defaults`, then `dl_compile_recipe` with typed bindings and presentation. Defaults follow generic → user → project → explicit reference → explicit call. Keep the returned `draft_reference` compact and pass it to validation/create; use its artifact path with exact target identity and fresh revision for update. Do not regenerate or echo the packaged renderer.

Validate the draft batch with `dl_editor_validate`; use `dl_object_diff` when a focused comparison helps. Create dependencies in order with `dl_object_create`, or update the requested object with `dl_object_update`. Both perform saved readback. When requested and supported for that object type, call `dl_object_publish` from a fresh saved revision and verify its published readback. Dataset and Connection have no invented publish lifecycle.

For new recipe chart placement, carry the compiled `visual_contract` into dashboard item `presentation`. Preserve explicit title/hint ownership and manual layout. Consult only relevant sections of [visualization decisions](../skills/datalens-dashboard/references/decision-quality.md) for KPI meaning, time, scales and accepted composition.

A clear request authorizes its scoped delivery steps without repeated plan/save/publish questions. A compact plan informs the user. Read-only permits no writes; save-only stops after saved readback. Ask only for unresolved target/scope conflicts or real access boundaries. Example:

> Update this chart, preserve neighboring widgets, save and publish it, and verify the result.

## Verify and reconcile

Separate Dataset query results, provider acceptance, saved/published identity and actual rendering. Use Browser read-only when rendered evidence is required, after API/readback and applicable data checks. An offline validator or configuration field does not prove the rendered result.

Writes return compact operation results. Use `dl_operation_get` for details and `dl_operation_reconcile` for an uncertain outcome. Do not blindly repeat a write after losing its response.

## Backup and scoped cleanup

Use [Maintenance](../skills/datalens-maintenance/SKILL.md). `dl_backup_export` exports snapshots; it does not claim a verified full restore. For authorized cleanup, `dl_cleanup_preview` computes dependency/preservation evidence; `dl_cleanup_apply` uses the unchanged exact `confirmed_delete` set and revalidates scope before writes. A clear deletion request already supplies human authorization; the machine scope is not a new human-click token. Reconcile changed previews against the request and stop for preservation conflicts or expanded scope. Failed/uncertain deletion stops remaining objects.

A list-only request performs no deletion. Preserve explicitly retained objects. A dashboard task does not authorize ACL changes, upstream production database writes, or unowned objects. See [authorized scope and delivery](../skills/datalens-dashboard/references/authorized-scope.md).
