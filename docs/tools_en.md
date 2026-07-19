# MCP tools

[Русский](tools.md) · **English** · [Project home](../README_en.md)

[Quick start](../README_en.md#quick-start) · [DataLens access](access_en.md) · [Connect](codex_setup_en.md) · **Tools** · [Workflows](usage-flow_en.md) · [Sources](sources_en.md) · [Safety](local-only-safety-model_en.md) · [Русский](tools.md)

The standard `tools/list` contains **38 tools**. Each exact JSON schema is available to the MCP client and summarized in the [technical catalog](mcp/tools.md). Common response shapes are documented in [response contracts](mcp/response_contracts.md).

Operation classes:

- `local` — works with configuration, supplied data, or files inside `--project-root`;
- `read-only API` — reads data through the DataLens Public API;
- `guarded write` — can save or publish after target, revision, and request checks;
- `local command` — runs a command declared in the project manifest.

## Setup and runtime

| Tool | Purpose | When to use | Required data | Result and class | Source |
| --- | --- | --- | --- | --- | --- |
| `dl_get_local_config` | Return effective local configuration without secret values | Check the workspace and execution settings | Optional config path and project root | Sanitized configuration · `local` | [Configuration](configuration_en.md) |
| `dl_runtime_status` | Show API, credential, write, save, publish, and token-refresh state | At session start and when an operation is blocked | Optional project root and local config | Diagnostic report without secret values · `local` | [Access](access_en.md#7-check-configuration-and-access) |
| `dl_auth_probe` | Run a minimal `getWorkbooksList` and refresh the token when needed | Before the first DataLens object read | Settings from `DATALENS_ENV_FILE` | Authentication result or precise error category · `read-only API` | [Public API](https://yandex.cloud/ru/docs/datalens/operations/api-start) |

## Object reads

| Tool | Purpose | When to use | Required data | Result and class | Source |
| --- | --- | --- | --- | --- | --- |
| `dl_list_workbooks` | List available workbooks | After a successful access check | Optional pagination | Workbook list · `read-only API` | [`getWorkbooksList`](https://yandex.cloud/ru/docs/datalens/openapi-ref/getWorkbooksList) |
| `dl_get_workbook_entries` | Read objects in one workbook | Find dashboards, charts, datasets, and connections | `workbook_id`, optional response mode | Entry list or a full-data artifact · `read-only API` | [`getWorkbookEntries`](https://yandex.cloud/ru/docs/datalens/openapi-ref/getWorkbookEntries) |
| `dl_get_entries_relations` | Read relations between entries | Before changing or deleting related objects | `entry_ids` | Dependency graph · `read-only API` | [`getEntriesRelations`](https://yandex.cloud/ru/docs/datalens/openapi-ref/getEntriesRelations) |
| `dl_read_object` | Read a known object type by ID | Get current saved or published state | `object_type`, `object_id`, optional branch | Object data or a full-response artifact · `read-only API` | [API method reference](https://yandex.cloud/ru/docs/datalens/openapi-ref/) |
| `dl_snapshot_dashboard` | Store a dashboard and its related objects | Before an audit, change, redesign, or backup | `dashboard_id`, optional `workbook_id` and branch | Files, manifest, and `complete` / `partial` / `unsafe` status · `read-only API` + `local` | [Dashboard model](https://yandex.cloud/ru/docs/datalens/concepts/dashboard/) |

## Reference and diagnostics

| Tool | Purpose | When to use | Required data | Result and class | Source |
| --- | --- | --- | --- | --- | --- |
| `dl_validate_editor_runtime_contract` | Check Editor JavaScript sections and methods | Before saving an Editor object | Object or sections/source | Findings with paths and lines · `local` | [Editor tabs](https://yandex.cloud/ru/docs/datalens/charts/editor/tabs) and [methods](https://yandex.cloud/ru/docs/datalens/charts/editor/methods) |
| `dl_classify_source_error` | Identify the stage and type of a data-source error | DataLens returned a sanitized error | `error_payload` | Category, stage, and remediation · `local` | [DataLens documentation](https://yandex.cloud/ru/docs/datalens/) and project rules |
| `dl_diagnose` | Analyze SQL, grain, relations, and performance from supplied data | Locate a cause or risk before writing | `mode`, evidence, optional project root | Concise findings and report paths · `local` | [Diagnostic contracts](mcp/response_contracts.md#diagnostics) |
| `dl_reference` | Search rules, recipes, formulas, and API method information | Resolve a capability, route, error, or source | `mode`, query or name, response limit | Up to five relevant records with sources · `local` | [Official sources](sources_en.md) |

## Change planning and validation

| Tool | Purpose | When to use | Required data | Result and class | Source |
| --- | --- | --- | --- | --- | --- |
| `dl_validate_project` | Check project files, requests, SQL, relations, and secrets | Before building an apply plan | Project root and optional context references | Findings and warnings · `local` | [Architecture](architecture.md) |
| `dl_build_payload_plan` | Compile validated materials into a DataLens request plan | After project and object validation | Project root, target, and request text | Methods, targets, and payloads without writing · `local` | [Safe apply](safe-apply_en.md) |
| `dl_build_validation_evidence_report` | Collect validation results by stage | Before handoff and after apply | Project root and report paths | Unified evidence report · `local` | [Response contracts](mcp/response_contracts.md) |
| `dl_validate_object` | Check an object against DataLens API schemas and safety rules | Before a create or update plan | `object_type`, `payload`, operation | Schema and policy findings without writing · `local` | [API Reference](https://yandex.cloud/ru/docs/datalens/openapi-ref/) |
| `dl_plan_object_create` | Build a create plan for a supported object | Create a dashboard, chart, dataset, or connection | `object_type`, `payload`, object location | Selected method, compiled payload, and blockers · `local` | [API Reference](https://yandex.cloud/ru/docs/datalens/openapi-ref/) |
| `dl_plan_object_update` | Build an update over current saved state | Change an existing object | `object_type`, current object, desired changes | Revision-preserving update plan · `local` | [Safe apply](safe-apply_en.md) |
| `dl_plan_guarded_dataset_update` | Plan dataset-model validation and update | Change fields, relations, or the dataset model | ID, current/proposed datasets, affected charts | GUID and chart-impact checks · `local` | [`validateDataset`](https://yandex.cloud/ru/docs/datalens/openapi-ref/validateDataset) |
| `dl_plan_dashboard_tab_update` | Prepare a bounded update to one dashboard tab | Append or replace a tab while preserving the rest | Current dashboard, tab, operation | Minimal dashboard update · `local` | [Dashboards](https://yandex.cloud/ru/docs/datalens/concepts/dashboard/) |
| `dl_reconcile_partial_creates` | Match a create plan with entries that already appeared | After an interrupted or uncertain create result | `workbook_id`, planned objects, optional entries | Reuse, create, or manual-review decision · `read-only API` + `local` | [Safe apply](safe-apply_en.md) |
| `dl_compile_guarded_rpc_request` | Compile a guarded request to one API method | Before an update enters the apply plan | Method, payload, ID, revision, and current readback | Request with a locked target and expected readback · `local` | [API contracts](sources_en.md#public-api-contracts) |

## Save and publish

| Tool | Purpose | When to use | Required data | Result and class | Source |
| --- | --- | --- | --- | --- | --- |
| `dl_create_safe_apply_plan` | Create a save plan with target, request hash, and checks | After validation and payload planning | Project root, actions, target, and request text | Executable plan or blockers · `local` | [Safe apply](safe-apply_en.md) |
| `dl_execute_safe_apply` | Execute plan actions with a fresh read and revision check | The request requires save or publish | `plan_path` and original request text | Request results and report artifacts · `guarded write` | [Normal change](usage-flow_en.md#normal-save-and-publish-change) |
| `dl_create_publish_from_saved_plan` | Build publishing from verified saved state | After save when the request requires publish | Project root, target, object type, saved readback | Plan with expected IDs and revision · `local` | [Publishing](safe-apply_en.md#publish-from-saved-state) |
| `dl_readback_and_report` | Read saved or published state and create a report | After save, publish, or a read-only check | Targets, branch, and execution result paths | Readback and report · `read-only API` + `local` | [Response contracts](mcp/response_contracts.md) |

## Manifest-backed projects

| Tool | Purpose | When to use | Required data | Result and class | Source |
| --- | --- | --- | --- | --- | --- |
| `dl_detect_project_live_workflows` | Find the project's command manifest | A project already owns validation and apply commands | `project_root` | Available workflows or a manifest request · `local` | [Project workflow](project_workflow.md) |
| `dl_plan_project_manifest` | Prepare or write the project manifest | No manifest exists | `project_root`, `write_manifest`, optional target IDs | Preview or written manifest · `local` | [Project workflow](project_workflow.md) |
| `dl_plan_project_live_workflow` | Resolve one declared action without running it | Before dry-run or apply | Project root, workflow, action, and request | Command, targets, environment, reports, and blockers · `local` | [Project workflow](project_workflow.md) |
| `dl_run_project_live_dry_run` | Run the declared validation command | After inspecting the plan | Project root, workflow, and `execute_now` | Sanitized output and report paths · `local command` | [Project workflow](project_workflow.md) |
| `dl_run_project_live_apply` | Run the declared save or publish action | The request requires applying a change | Project root, workflow, action, and request | Execution summary and reports · `guarded write` + `local command` | [Project workflow](project_workflow.md) |
| `dl_read_project_live_summary` | Read and validate the project's JSON summary | After dry-run, save, or publish | Project root, action, or summary path | Changed objects, state, and errors · `local` | [Project workflow](project_workflow.md) |

## Maintenance and source availability

| Tool | Purpose | When to use | Required data | Result and class | Source |
| --- | --- | --- | --- | --- | --- |
| `dl_run_live_maintenance_update` | Coordinate a bounded fix from supplied validation results | Fix a known chart or tab | Target, request, current/proposed data, reports | Delivery stage and handoff report · `local` | [Safe apply](safe-apply_en.md) |
| `dl_build_dashboard_source_availability_matrix` | Build source state for dashboard consumers | Objects depend on different tables or environments | Dashboard snapshot and source-check results | `OK`/`NO_DATA`/`NO_TABLE`/`ERROR`/`UNKNOWN` matrix · `local` | [Diagnostic contracts](mcp/response_contracts.md#diagnostics) |
| `dl_validate_source_availability_consumers` | Validate consumers against one source matrix | Before a source-dependent change | Matrix and consumer requirements | Conflicts and stopping reasons · `local` | [Diagnostic contracts](mcp/response_contracts.md#diagnostics) |
| `dl_plan_source_availability_patch` | Plan a bounded correction from the source matrix | After validating the matrix | Matrix, target, and desired correction | Plan without querying source systems · `local` | [Safe apply](safe-apply_en.md) |

## API catalog

| Tool | Purpose | When to use | Required data | Result and class | Source |
| --- | --- | --- | --- | --- | --- |
| `dl_list_api_methods` | List known DataLens methods and support status | Check which operation is available | Optional filters and limit | Compact catalog with compiled OpenAPI SHA/version · `local` | [DataLens API Reference](https://yandex.cloud/ru/docs/datalens/openapi-ref/) |
| `dl_get_api_method_schema` | Return one method schema | Inspect required fields before planning | `method` | Request fields, usage policy, and documentation URL · `local` | [DataLens API Reference](https://yandex.cloud/ru/docs/datalens/openapi-ref/) |
