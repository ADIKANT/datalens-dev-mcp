# Usage workflows

[Русский](usage-flow.md) · **English** · [Project home](../README_en.md)

[Quick start](../README_en.md#quick-start) · [DataLens access](access_en.md) · [Connect](codex_setup_en.md) · [Tools](tools_en.md) · **Workflows** · [Sources](sources_en.md) · [Safety](local-only-safety-model_en.md) · [Русский](usage-flow.md)

Codex, Claude, and other stdio clients use the same lifecycle. Only server registration differs.

## Complete flow

```text
connect the MCP client
  -> check local settings
  -> check live DataLens access
  -> find the workbook
  -> read the target and relations
  -> plan the change
  -> validate the object and project
  -> save
  -> read saved state
  -> publish from saved state
  -> read published state
  -> verify the result in DataLens
```

The request selects the stopping point. The server does not ask again before save or publish after the user has requested a create, fix, update, enhancement, or redesign of a known object. Deleting a complete object requires a separate confirmation.

## Connection and preflight

1. Install the package using the [quick start](../README_en.md#quick-start).
2. Configure `yc`, organization ID, IAM token, and roles using [DataLens access](access_en.md).
3. Register the stdio server. Codex users can follow the [step-by-step guide](codex_setup_en.md).
4. Restart the client and check the connection.
5. Call `dl_runtime_status`, then `dl_auth_probe`.

Prompt:

> Use the DataLens MCP server. Show `dl_runtime_status`: project root, API version, credential presence without values, and write, save, publish, and token-refresh availability. Then call `dl_auth_probe`. Do not change anything in this step.

`dl_runtime_status` checks local configuration. `dl_auth_probe` calls `getWorkbooksList` and can obtain or refresh an IAM token through the configured `yc` CLI.

## Read-only audit

Use this mode to understand a dashboard, locate a problem, or prepare recommendations.

```text
dl_runtime_status
  -> dl_auth_probe
  -> dl_list_workbooks
  -> dl_get_workbook_entries
  -> dl_snapshot_dashboard
  -> dl_read_object
  -> dl_get_entries_relations
  -> dl_diagnose or dl_reference when needed
```

For an existing dashboard, `dl_snapshot_dashboard` stores the dashboard and
related objects. `completion.status` distinguishes `complete`, `partial`, and
`unsafe`; `coverage.scope=dashboard_dependency_graph` is not a claim about the
whole space or organization. `dl_get_entries_relations` shows dependencies that
must be considered before a change.

Prompt:

> Audit dashboard `<DASHBOARD_ID>` in workbook `<WORKBOOK_ID>`. Read the current saved version, capture it with related objects, inspect relations, and identify risks. Return concise findings and report paths. Do not save or publish anything.

## Plan without writing

Use `plan-only` to inspect the future API request and validation results.

```text
current readback
  -> dl_plan_object_create or dl_plan_object_update
  -> dl_validate_object
  -> dl_validate_editor_runtime_contract for Editor work
  -> dl_validate_project
  -> dl_build_payload_plan
  -> dl_create_safe_apply_plan
  -> stop without dl_execute_safe_apply
```

Use `dl_plan_guarded_dataset_update` for dataset-model changes and `dl_plan_dashboard_tab_update` for a single dashboard tab.

Prompt:

> Plan a change to `<OBJECT_TYPE>` `<OBJECT_ID>`: `<REQUIREMENT>`. Read current saved state and relations, then show the selected API method, changed fields, preserved revision, and validation results. Stay plan-only: do not save or publish.

## Save without publishing

`save-only`, `no-publish`, and “save without publishing” stop after saved readback.

```text
current readback and validation
  -> dl_create_safe_apply_plan
  -> dl_execute_safe_apply
  -> dl_readback_and_report for saved state
  -> stop
```

Prompt:

> Update `<OBJECT_TYPE>` `<OBJECT_ID>`: `<REQUIREMENT>`. Read current saved state, validate the change, save it, and verify saved state. Use save-only mode and do not publish.

If publishing is hard-disabled with `DATALENS_MCP_LIVE_ALLOW_PUBLISH=0`, the server completes the permitted save and returns `saved_not_published`.

## Normal save-and-publish change

“Create”, “fix”, “update”, “enhance”, and “redesign” run the complete flow for a known object.

```text
current readback and relations
  -> planning and validation
  -> dl_create_safe_apply_plan
  -> dl_execute_safe_apply
  -> dl_readback_and_report for saved state
  -> dl_create_publish_from_saved_plan
  -> dl_execute_safe_apply
  -> dl_readback_and_report for published state
  -> verify the changed area in DataLens
```

Publishing is built from the saved readback result. The server checks the ID, revision, and saved version before every write request.

Prompt:

> Fix `<OBJECT_TYPE>` `<OBJECT_ID>` in workbook `<WORKBOOK_ID>`: `<REQUIREMENT>`. Read current saved state and relations, plan and validate the change, save it, verify saved state, publish from the saved version, and verify the published result. Do not ask for another confirmation before save or publish. If UI verification is unavailable, state that limitation in the result.

For a visible chart or dashboard change, final verification should cover the changed tab or object. API readback verifies structure; UI verification confirms rendering.

## Delete a complete object

Deleting a complete dashboard, chart, dataset, connection, or another object takes two calls:

1. the server builds a plan and returns the type, exact ID, relations, and plan hash with `delete_confirmation_required`;
2. the user confirms that deletion, and the same plan runs with `confirm_delete=true`.

If the object or plan changes, the confirmation no longer applies and the server builds a new plan. Removing an element inside an object, such as a legend, filter, column, tab, or widget, is a normal update.

Prompt:

> Delete complete `<OBJECT_TYPE>` `<OBJECT_ID>`. First show the exact object, relations, and deletion plan. Execute only after my separate confirmation of that plan.

## Manifest-backed projects

When a project already defines its validation and apply commands, the server uses that declared process:

```text
dl_detect_project_live_workflows
  -> dl_plan_project_manifest when no manifest exists
  -> dl_plan_project_live_workflow
  -> dl_run_project_live_dry_run
  -> dl_read_project_live_summary
  -> dl_run_project_live_apply
  -> dl_read_project_live_summary
```

The manifest records commands, object IDs, allowed environment names, expected reports, and checks. The server runs only declared actions.

## When the flow stops

| State | Check |
| --- | --- |
| `missing_credentials` | `DATALENS_ENV_FILE`, organization ID, and `yc` setup |
| `expired_token` | `yc` authentication and `DATALENS_ENABLE_TOKEN_REFRESH_ON_401=1` |
| `organization_access_denied` | Organization and role on the target workbook |
| Stale revision | Repeat the current read and rebuild the plan |
| Lock or uniqueness conflict | Reconcile current object state; do not retry blindly |
| `saved_not_published` | Publish is disabled or the request contains `save-only`/`no-publish` |
| No UI verification | Run the DataLens check or report the limitation explicitly |

## Other MCP clients

Claude Code, Claude Desktop, and other stdio clients launch the same command with the same `DATALENS_ENV_FILE` and `--project-root`. Examples are under [`examples/clients/`](../examples/clients/). Use the same workflows and state the desired stopping point in the task.
