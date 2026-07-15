# Server usage flow

[Русский](usage-flow.md) · **English** · [Documentation](README_en.md) · [Tools](tools_en.md) · [Codex setup](codex_setup_en.md)

The flow is the same for Codex, Claude, and any other MCP client. Only stdio process registration differs; the server defines the tool sequence, safety gates, and response contracts.

## 1. Connection and preflight

1. Install the package and configure an external env file from the [README](../README_en.md#installation).
2. Register the stdio server in the client. For Codex, follow the [step-by-step guide](codex_setup_en.md).
3. Restart the client after changing MCP configuration.
4. Confirm the server and standard tool surface are available.
5. Call `dl_runtime_status`, followed by `dl_auth_probe`.

A safe first run should show:

- `allow_writes=false`;
- `allow_save=false`;
- `allow_publish=false`;
- `expert_rpc_enabled=false`;
- the intended `project_root`;
- auth presence without token values, prefixes, or lengths.

Codex prompt:

> Use only the public DataLens MCP tools. Call `dl_runtime_status`, show the project root, API version, and mutation gates, then run `dl_auth_probe`. Do not change anything. Do not expose credentials or token-derived data.

## 2. Read-only audit

The goal is to collect evidence about the exact live target before making decisions.

```text
dl_runtime_status
  -> dl_auth_probe
  -> dl_list_workbooks
  -> dl_get_workbook_entries
  -> dl_snapshot_dashboard
  -> dl_read_object / dl_get_entries_relations
  -> dl_reference or dl_diagnose when needed
```

Recommended sequence:

1. Select a workbook from `dl_list_workbooks`.
2. Get a compact inventory with `dl_get_workbook_entries`.
3. Always create a fresh `dl_snapshot_dashboard` for an existing dashboard.
4. Read concrete charts/datasets/connections with `dl_read_object`.
5. Read the relation graph with `dl_get_entries_relations` before changing a related object.
6. Use `dl_reference` for bounded official/local policy context and `dl_diagnose` for SQL, grain, or performance evidence.

Prompt:

> Run a read-only audit of dashboard `<DASHBOARD_ID>` in workbook `<WORKBOOK_ID>`. Check runtime and auth first, then create a full dashboard graph snapshot, read related objects, and read the relation graph. Return a compact object list, revision/branch evidence, risks, and artifact paths. Do not save or publish.

If credentials are missing, the server returns `BLOCKED_LIVE_CREDENTIALS`. Correct the external env file and restart the MCP process; never paste the token into chat.

## 3. Plan-only

Plan-only turns fresh readback and requirements into a validated no-write plan.

```text
fresh snapshot/readback
  -> dl_reference(mode="chart_selection" or "api_contract")
  -> dl_plan_object_create / dl_plan_object_update
  -> specialized planner when needed
  -> dl_validate_object
  -> dl_validate_editor_runtime_contract when Editor is involved
  -> dl_validate_project
  -> dl_build_payload_plan
  -> dl_create_safe_apply_plan (unapproved)
```

Planner selection:

- standard create/update: `dl_plan_object_create` or `dl_plan_object_update`;
- dataset model change: `dl_plan_guarded_dataset_update`;
- one dashboard tab: `dl_plan_dashboard_tab_update`;
- uncertain create retry: call `dl_reconcile_partial_creates` first;
- exact RPC contract before apply: `dl_compile_guarded_rpc_request`.

New standard charts use `wizard_native`. Advanced Editor requires a direct request or a registered capability gap. QL create/update requires a direct QL request and is never a fallback.

Prompt:

> From fresh saved readback, plan this change to `<OBJECT_ID>`: `<REQUIREMENT>`. Show the selected route, official API method, desired overlay, preserved revision/unknown fields, validation findings, and an unapproved safe-apply plan. Stay plan-only: do not enable gates or execute a write.

Before live apply, target IDs, changed sections, blockers, readback mode, and intended delivery state must be explicit.

## 4. Guarded save and publish

A live write starts only after plan review and explicit enablement of required gates in the external env file. Restart the MCP process after changing the file.

### Save

```text
approved safe-apply plan
  -> dl_execute_safe_apply(mode=save)
  -> fresh read immediately before write
  -> revision-preserving save
  -> saved readback
  -> dl_readback_and_report(branch=saved)
```

Save requires `DATALENS_MCP_ENABLE_WRITES=1`, `DATALENS_MCP_LIVE_ALLOW_SAVE=1`, tool approval, fresh saved readback, a validated payload, and an approved plan. `draft`, `review`, `plan-only`, `save-only`, and `no-publish` do not permit publishing.

Save-only prompt:

> Apply the approved plan to the known target in save-only mode. Fresh-read before writing, preserve revision and unknown fields, then perform saved readback and create a deployment report. Do not create a publish plan or publish.

### Publish-from-saved

```text
verified saved readback
  -> saved runtime gate when the change is visible
  -> dl_create_publish_from_saved_plan
  -> dl_execute_safe_apply(publish action)
  -> published readback
  -> dl_readback_and_report(branch=published)
```

Publishing is allowed only from a saved-branch artifact with expected `revId` and `savedId`, a `save_then_publish`/`publish_from_saved` delivery intent, and `DATALENS_MCP_LIVE_ALLOW_PUBLISH=1`. A publish plan cannot be built from a published or unknown branch.

Full guarded delivery prompt:

> Implement the agreed change to the known target using the approved safe-apply plan and enabled runtime gates. Save, perform saved readback, run runtime smoke on the changed visible scope, then publish only from the verified saved artifact. Finish with published readback and a deployment report. If browser/runtime proof is unavailable, return `runtime_not_verified`, not `done`.

## 5. Runtime and browser QA

API readback proves structure, not browser rendering. Acceptance for a changed visible chart/tab follows this order:

1. browser/runtime smoke on the changed scope;
2. sanitized details from a DataLens error card when present;
3. targeted source evidence;
4. saved/published readback as structural proof;
5. `validateDataset` only as a schema/compile hint for dataset changes.

The `dl_run_live_maintenance_update` MCP tool does not open a browser or execute a DataLens write. It validates supplied guarded-execution and runtime evidence, computes the delivery stage, and writes a final handoff artifact. Codex can collect browser evidence with a separate available browser/computer tool and pass it to the MCP planner.

A final visible change has one of these statuses:

- `done` — runtime gate passed or an explicit non-rendering exemption exists;
- `runtime_not_verified` — browser auth/tooling prevented verification;
- `blocked` — a runtime marker or missing safety gate blocks completion;
- `rolled_back` — a confirmed rollback was performed.

## 6. Project-live repositories

When a downstream project already has guarded scripts, do not run them directly. Use the manifest-backed lane:

```text
dl_detect_project_live_workflows
  -> dl_plan_project_manifest when missing
  -> dl_plan_project_live_workflow
  -> dl_run_project_live_dry_run
  -> dl_read_project_live_summary
  -> dl_run_project_live_apply when approved
  -> dl_read_project_live_summary
```

The manifest records exact argv, object IDs, allowed env names, expected artifacts, evidence checks, and safety constraints. A missing manifest returns `adapter_required`. Named object removal is not added to normal publish; it uses the separate `retire_legacy_objects` lifecycle.

## 7. Common stop states

| State | Meaning | Next action |
| --- | --- | --- |
| `BLOCKED_LIVE_CREDENTIALS` | No usable org ID/token | Correct the external env file and restart the process |
| `adapter_required` | Project scripts have no manifest | Preview `dl_plan_project_manifest`, review it, then approve the local write |
| Stale revision/readback | Target changed after planning | Repeat fresh read and rebuild the overlay and plan |
| `conflict_no_write` | Lock or uniqueness conflict | Do not retry blindly; wait for the lock or reconcile identity |
| `write_outcome_unknown` | No classified result after a write attempt | Stop and run read-only reconciliation |
| `runtime_not_verified` | Structure is proven but render proof is missing | Run browser smoke or hand off without claiming `done` |

## 8. Clients other than Codex

Claude Code, Claude Desktop, and generic stdio clients use the same server command, env file, and `--project-root`; registration examples are in the [README](../README_en.md#connect-an-mcp-client). After connecting, start with the same `dl_runtime_status` → `dl_auth_probe` flow and do not ask the model to select a hidden tool profile.
