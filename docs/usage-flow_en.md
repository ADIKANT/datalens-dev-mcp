# Usage workflows

[Русский](usage-flow.md) · **English** · [Project home](../README_en.md)

[Quick start](../README_en.md#quick-start) · [DataLens access](access_en.md) · [Connect](codex_setup_en.md) · [Tools](tools_en.md) · **Workflows** · [Sources](sources_en.md) · [Safety](local-only-safety-model_en.md) · [Русский](usage-flow.md)

Codex, Claude, and other stdio clients use the same lifecycle. Only server registration differs. By default the client sees eight `autonomous-v2` task-level tools; the server performs the low-level steps listed below inside the workflow.

The final live proof is separate from offline regression. Once the source tree
is frozen, one dedicated-target canary drives the installed wheel through
public stdio: one save, restart, resume, one publish, typed dataset proof, and a
stale-plan negative with zero writes. See
[`public-autonomy-canary.md`](public-autonomy-canary.md) for the exact contract.

### Creating an object set in a known workbook

For a `create` request, pass `context.workbook_id` and a
`context.create_manifest` path relative to `project_root`. The version 1
manifest contains at most 25 objects with typed routes, relative JSON payload
files, and explicit dependencies. A `${object:<key>}` reference is resolved only
after the preceding object has a verified saved readback. The server hashes the
manifest and payloads before the first write, reads fresh workbook inventory,
and journals progress so resume cannot blindly repeat a create.

Supported types are `dataset`, `wizard_chart`, `editor_chart`,
`editor_markdown`, and `dashboard`; `ql_chart` requires a direct QL request.
Absolute/path escapes, payload drift, invalid dependency order, and ambiguous
resume fail before the next write. Datasets receive save/readback but no
publish; publishable objects advance only after the related group completes its
saved phase.

## Autonomous task workflow

```text
dl_task_start(request, run_until="plan_ready")
  -> dl_task_status / dl_inspect when needed
  -> dl_plan to reread the hash-bound plan explicitly
  -> dl_execute(task_id, plan_hash) for write tasks
     or dl_task_resume to continue the server-owned workflow
  -> dl_verify
  -> dl_evidence for one bounded artifact
```

`dl_task_start` compiles immutable target, delivery, evidence, and browser policy fields, writes the event chain, and normally stops at `PLAN_VALIDATED`. `dl_task_resume` continues the same task after a process restart; `expected_state` and `expected_hash` prevent execution from stale state. Review, audit, diagnose, and plan-only tasks finish without writes. A write task uses the persisted Safe Apply plan and does not accept arbitrary model-supplied payloads at `dl_execute` time.

Full plans, receipts, and evidence are read through `datalens://tasks/<TASK_ID>/...`; the inline response remains compact. Existing clients can enable `DATALENS_MCP_TOOL_SURFACE=legacy-v1` locally, but the new autonomous flow does not require direct internal tool calls.

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

The request selects the stopping point. Before a substantial mutation the
server returns one compact plan; that confirmation covers unchanged save and
publish. Destructive cleanup is limited to exact run-owned objects with an
ownership receipt and requires a separate exact-object token.

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

## Fast standalone HTML generation and delivery

Start with one local cycle for the self-contained document:

```text
dl_generate_editor_bundle with html_page
  -> dl_validate_editor_runtime_contract for the generated .html
  -> ready local artifact
```

The generator returns the path, size, hash, and validation result without
duplicating HTML in the MCP response, and performs no live write itself. To
deliver into a known workbook, pass validated `content` through the ordinary
lifecycle:

```text
dl_plan_object_create with object_type=html_page
  -> dl_create_safe_apply_plan
  -> dl_execute_safe_apply:
       createHtmlPage
       getHtmlPage(saved)
       updateHtmlPage(entryId, revId, mode=publish)
       getHtmlPage(published)
```

Updates use `updateHtmlPage` with new content for save and only the verified
saved `revId` for publish. `deleteHtmlPage` remains closed under the shared
whole-object deletion policy. See the
[HTML-page guide](datalens/html_pages_en.md).

Prompt:

> Create a self-contained HTML page in workbook `<WORKBOOK_ID>`: `<REQUIREMENT>`. Generate and validate the local artifact, then create `html_page` through Safe Apply, read saved state, publish its `revId`, and verify published state.

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
  -> dl_execute_safe_apply:
       save the complete group
       saved readback for the complete group
       one all-object publish preflight
       publish the complete group
       published readback for the complete group
  -> verify the changed area in DataLens
```

Publishing is built from the saved readback result. The server checks the ID, revision, and saved version before every write request.
`dl_create_publish_from_saved_plan` is an explicit resume tool for a previously
stopped saved artifact, not a required second plan in the normal flow.

Prompt:

> Fix `<OBJECT_TYPE>` `<OBJECT_ID>` in workbook `<WORKBOOK_ID>`: `<REQUIREMENT>`. Read current saved state and relations, show one compact plan for confirmation, save it, verify saved state, publish from the saved version, and verify the published result. If UI verification is unavailable, state that limitation in the result.

For a visible chart or dashboard change, final verification should cover the changed tab or object. API readback verifies structure; UI verification confirms rendering.

## Standard dashboard build path

Create and full-redesign calls default to `standard_dashboard`;
`strict_dashboard` is an alias. It fixes Wizard-first decisions and applies the
same profile's protected renderer only to selected Editor objects. Historical
profile names are input aliases that normalize to `standard_dashboard`, so
both new and existing dashboards use one current contract.

One batch may contain up to 100 unique widgets and returns compact statuses,
artifact paths, and hashes. It also writes a hash-bound
`dashboard_composition` skeleton. `dl_validate_project` rebuilds the
actual final payload and emits `final_payload_attestation`; a later route,
runtime, title, selector, layout, or payload change invalidates it.

The contract binds the exact `display_title` and role-based `title_mode`, the
protected renderer, left-labelled selector rows at exactly 94 percent, a
gap-free 36-column layout with equal peer heights, and no more than three
standard KPI cards per row.

Final Browser QA runs only after publish/readback and API-first diagnostics. It
checks every required tab from top to its real bottom, including lazy loading,
clipping/overlap, title/hint ownership, tooltip, legend, comparison context,
and runtime errors. Default acceptance does not change selectors or filters;
interaction testing is a separate explicit cell with baseline/restore. An
unattributed visible error keeps acceptance open. Publish does not depend on
Browser; `done` requires published readback and verifiable per-tab Browser
receipts for the exact target.

## Fast path for merging date selectors

When the selector and dashboard IDs are known, two static date controls can be
merged with
`maintenance_contract.kind=date_range_selector_merge`.

```text
exact selector saved-read + exact dashboard saved-read
  -> one dl_create_safe_apply_plan with maintenance_contract
  -> one dl_execute_safe_apply with saved/published readbacks
  -> one targeted browser smoke and one capture
```

The contract takes two readback artifact paths, exact object IDs,
`param_from`/`param_to`, label, defaults, `option_source=none`, reset policy,
and an optional `mounted_control_id`. Without an explicit mount ID, exactly one
mount may match the source selector ID. Dynamic or ambiguous JavaScript,
mismatched IDs/revisions, multiple mounts, Params/default drift, and
`updateControlsOnChange: true` on the canonical range block the plan before
writing.

The budget is two initial exact reads and at most 14 RPCs including
save/readback/publish/readback, with one plan and one executor.
`dl_snapshot_dashboard`, workbook inventory, dataset live validation, and
reference search are outside this path. Runtime smoke must see one range,
apply both boundaries, verify them after rerender and reload, check for no
DOM/console errors, and store one capture.

## Delete a complete object

The standard lifecycle tools do not execute arbitrary whole-object deletion.
The supported path is a `retire_legacy_objects` action declared by a project
manifest, and it takes two calls:

1. `dl_run_project_live_apply` builds a plan and returns the exact IDs and plan hash with `delete_confirmation_required`;
2. the user confirms that unchanged plan, and the call repeats with `confirm_delete=true`.

If the target or plan changes, the confirmation no longer applies. Removing an
element inside an object, such as a legend, filter, column, tab, or widget, is a
normal update. Whole-object QL deletion is unsupported.

Prompt:

> Run the `retire_legacy_objects` action declared by the project manifest. First show the exact IDs and plan hash. Execute the same plan only after my separate confirmation.

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
