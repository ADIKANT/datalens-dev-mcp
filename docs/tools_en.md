# Public MCP tools

[Русский](tools.md) · **English** · [Documentation](README_en.md) · [Flow](usage-flow_en.md) · [Sources](sources_en.md)

Normal `tools/list` returns one standard surface of **38 tools**. Every tool is described exactly once below. Compatibility/test-only helpers are intentionally excluded: they are not a user profile and must not appear in normal workflows.

Operation classes:

- `local` — operates on configuration, supplied evidence, or files inside `--project-root`; it does not mutate DataLens;
- `read-only API` — performs reads through the DataLens Public API only;
- `guarded write` — can cause a live mutation only with approval, enabled gates, a fresh read, and readback;
- `local command` — runs only a command declared in a project-live manifest.

For exact JSON inputs and response shapes, see the [technical catalog](mcp/tools.md) and [response contracts](mcp/response_contracts.md).

## Setup and runtime

| Tool | Purpose | When to use | Main input | Result and class | Basis |
| --- | --- | --- | --- | --- | --- |
| `dl_get_local_config` | Return merged local configuration without secret values | Check project root, defaults, and policy overrides | Optional config path/project root | Sanitized effective config · `local` | [Local configuration](configuration.md) |
| `dl_runtime_status` | Show API version, auth presence, route policy, and mutation gates | First call in every session and for unexpected blocks | No required input | Secret-safe runtime status · `local` | [Safety model](local-only-safety-model.md) |
| `dl_auth_probe` | Run a minimal `getWorkbooksList` probe | Before any live read | Credentials from the external env file | Auth success or sanitized blocker · `read-only API` | [Public API/auth](sources_en.md#public-api-contracts) |

## Read and discovery

| Tool | Purpose | When to use | Main input | Result and class | Basis |
| --- | --- | --- | --- | --- | --- |
| `dl_list_workbooks` | List workbooks available to the account | After a successful auth probe | Pagination/filter options | Compact workbook list · `read-only API` | `getWorkbooksList` in the [API Reference](https://yandex.cloud/ru/docs/datalens/openapi-ref/getWorkbooksList) |
| `dl_get_workbook_entries` | Read entries in one workbook | Inventory charts, datasets, connections, and dashboards | `workbook_id`, response mode | Compact entries or artifact-backed full data · `read-only API` | `getWorkbookEntries` in the [API Reference](https://yandex.cloud/ru/docs/datalens/openapi-ref/getWorkbookEntries) |
| `dl_get_entries_relations` | Return the relation graph for entries | Before changing related objects or using the retire lifecycle | Entry IDs | Sanitized dependency graph · `read-only API` | `getEntriesRelations` in the [API Reference](https://yandex.cloud/ru/docs/datalens/openapi-ref/getEntriesRelations) |
| `dl_read_object` | Read a supported object through one high-level interface | When a concrete object type and ID are known | `object_type`, `object_id`, branch/response mode | Compact object contract or artifact · `read-only API` | [API method map](sources_en.md#public-api-contracts) |
| `dl_snapshot_dashboard` | Store a full dashboard graph snapshot and related objects | Before an audit, fix, redesign, or backup | `dashboard_id`, branch/readback options | Sanitized snapshot artifacts and manifest · `read-only API + local` | Dashboard/object reads in the [API Reference](https://yandex.cloud/ru/docs/datalens/openapi-ref/) |

## Reference and diagnostics

| Tool | Purpose | When to use | Main input | Result and class | Basis |
| --- | --- | --- | --- | --- | --- |
| `dl_validate_editor_runtime_contract` | Validate Advanced Editor HTML/JS and allowed `Editor.*` methods | Before payload planning and saving an Editor object | Hydrated/generated Editor sections | Findings with rule/path/line · `local` | [Editor tabs and methods](sources_en.md#primary-official-pages) |
| `dl_classify_source_error` | Separate auth, connection, SQL, renderer, and sanitizer failures | When DataLens returns a sanitized error payload | `error_payload` | Stage/category/remediation · `local` | [DataLens docs + local classifier](sources_en.md#three-layers-of-truth) |
| `dl_diagnose` | Analyze SQL, grain, semantic graph, performance, and optimization evidence | Locate a cause or risk before apply | `mode` and bounded supplied evidence | Compact findings + artifact paths · `local` | [Local diagnostics contract](mcp/response_contracts.md#sql-and-performance-diagnostics) |
| `dl_reference` | Find bounded source-traced rules, recipes, formulas, and API policy | Resolve a route, capability, error, or source trace | `mode`, query/name, char budget | Up to five rules, next tools, and source metadata · `local` | [Packaged docs provenance](sources_en.md#documentation-snapshot) |

## Validation and object lifecycle planning

| Tool | Purpose | When to use | Main input | Result and class | Basis |
| --- | --- | --- | --- | --- | --- |
| `dl_validate_project` | Validate routes, bundles, payloads, SQL, privacy, and dashboard contracts | Before building a live payload plan | `project_root` and validation options | Pass/blocking report · `local` | [Local policy](sources_en.md#three-layers-of-truth) |
| `dl_build_payload_plan` | Compile validated artifacts into a dry-run DataLens payload plan | After project/object validation | Project artifacts and target metadata | Intended methods/targets/files, no write · `local` | [API contracts + Safe Apply](safe-apply.md) |
| `dl_build_validation_evidence_report` | Separate static, API, save, publish, and browser evidence | Before handoff and after a controlled run | Evidence/artifact paths | Proof-level report · `local` | [Proof levels](safe-apply.md#proof-levels) |
| `dl_validate_object` | Validate an object payload against compiled schemas and safety policy | Before a create/update planner | `object_type`, payload | Schema/policy findings, no mutation · `local` | [Compiled API contracts](sources_en.md#public-api-contracts) |
| `dl_plan_object_create` | Build a guarded create plan for a supported object type | Create a dashboard/chart/dataset/connection with a known location | `object_type`, named source adapter/payload | Method, compiled payload, blockers · `local` | Create methods in the [API Reference](https://yandex.cloud/ru/docs/datalens/openapi-ref/) |
| `dl_plan_object_update` | Build an update plan from fresh saved readback | Change an existing object | `object_type`, fresh object and desired overlay | Revision-preserving update plan · `local` | Update methods + [Safe Apply](safe-apply.md) |
| `dl_plan_guarded_dataset_update` | Plan `getDataset` → `validateDataset` → `updateDataset` → saved readback | Change dataset fields or model | Dataset ID, current/proposed dataset, affected chart refs | GUID preservation and blocking report · `local` | Dataset methods in the [API Reference](https://yandex.cloud/ru/docs/datalens/openapi-ref/validateDataset) |
| `dl_plan_dashboard_tab_update` | Append or replace one tab while preserving the rest of the dashboard | Make a bounded tab change | Fresh dashboard, tab, replace/append intent | Minimal dashboard overlay plan · `local` | [Dashboard model](https://yandex.cloud/ru/docs/datalens/concepts/dashboard/) |
| `dl_reconcile_partial_creates` | Match planned creates with entries that already appeared | Before retrying an uncertain or partial create | Workbook ID, planned objects, optional entries payload | Reuse/create/manual-review decisions · `read-only API + local` | Workbook inventory + [Safe Apply](safe-apply.md) |
| `dl_compile_guarded_rpc_request` | Record method, target, base revision, payload hash, and readback contract | Before an update enters safe apply | Method, payload, fresh-read and branch metadata | Guarded RPC request artifact · `local` | [Compiled API contracts](sources_en.md#public-api-contracts) |

## Safe apply, save, and publish

| Tool | Purpose | When to use | Main input | Result and class | Basis |
| --- | --- | --- | --- | --- | --- |
| `dl_create_safe_apply_plan` | Create an unapproved save-first plan | After validation and payload planning | Project root, targets/actions, readback mode | Guarded plan with blockers and approval state · `local` | [Safe Apply](safe-apply.md) |
| `dl_execute_safe_apply` | Execute approved actions with fresh read and revision preservation | Only after review and enabling required gates | Approved plan, runtime/tool approval | Save/publish action results and artifacts · `guarded write` | [Safe Apply](safe-apply.md) |
| `dl_create_publish_from_saved_plan` | Create a publish action from saved readback only | After successful save and saved runtime gate when intent permits publish | Saved readback artifact, target/type | Plan with expected `revId`/`savedId` · `local` | [Explicit publish lane](safe-apply.md#explicit-publish-lane) |
| `dl_readback_and_report` | Read saved/published state and create a deployment report | After save, publish, or offline dry run | Targets, branch, execution/readback artifacts | Compact proof + deployment report · `read-only API + local` | [Response contract](mcp/response_contracts.md#safe-apply-savepublishreadback-plan) |

## Project-live manifest workflow

| Tool | Purpose | When to use | Main input | Result and class | Basis |
| --- | --- | --- | --- | --- | --- |
| `dl_detect_project_live_workflows` | Find an allowlisted project manifest or request an adapter | Work in a downstream repository with its own scripts | `project_root` | Detected workflows or `adapter_required` · `local` | [Project workflow](project_workflow.md) |
| `dl_plan_project_manifest` | Preview a manifest and optionally perform an approved local write | A project has no manifest | `project_root`, approval/write flag | Proposed manifest or approved file · `local` | [Project workflow](project_workflow.md) |
| `dl_plan_project_live_workflow` | Parse a declared action without running it | Before dry-run/apply/retire | Project root, workflow/action | Exact argv, targets, env names, evidence checks · `local` | [Project workflow](project_workflow.md) |
| `dl_run_project_live_dry_run` | Run only a manifest-declared dry-run in an allowlisted environment | After reviewing the plan and setting `execute_now=true` | Project/action, manifest permissions | Redacted stdout/stderr and summary pointers · `local command` | [Project-live policy](policy_vocabulary.md) |
| `dl_run_project_live_apply` | Run an approved manifest apply/publish action behind live gates | A project already has a guarded executor | Project/action, approval and runtime gates | Execution summary/evidence · `guarded write + local command` | [Project-live policy](project_workflow.md) |
| `dl_read_project_live_summary` | Normalize declared JSON summary and validate evidence coverage | After dry-run/apply or during an audit | Project root, action/summary path | Changed counts, branch state, blockers · `local` | [Manifest summary](policy_vocabulary.md) |

## Maintenance and source availability

| Tool | Purpose | When to use | Main input | Result and class | Basis |
| --- | --- | --- | --- | --- | --- |
| `dl_run_live_maintenance_update` | Plan and validate runtime-first maintenance from supplied evidence | Make a bounded fix to a known live target | Target/intent, guarded execution and runtime evidence | Delivery stage/final handoff artifact; no direct write · `local` | [Delta v8](safe-apply.md#delta-v8-runtime-first-default) |
| `dl_build_dashboard_source_availability_matrix` | Build one availability matrix from supplied evidence | Tabs/charts depend on different source states | Source/environment/consumer evidence | `OK`/`NO_DATA`/`NO_TABLE`/`ERROR`/`UNKNOWN` rows · `local` | [Source evidence contract](mcp/response_contracts.md#sql-and-performance-diagnostics) |
| `dl_validate_source_availability_consumers` | Validate consumers against one availability truth | Before a source-related publish | Matrix and consumer requirements | Conflicts and publish blockers · `local` | [Local maintenance policy](safe-apply.md) |
| `dl_plan_source_availability_patch` | Plan a bounded correction without querying systems itself | After validating the availability matrix | Matrix, target, and desired correction | No-write patch plan · `local` | [Local maintenance policy](safe-apply.md) |

## API catalog

| Tool | Purpose | When to use | Main input | Result and class | Basis |
| --- | --- | --- | --- | --- | --- |
| `dl_list_api_methods` | List curated DataLens methods and support status | Check whether an operation exists and is allowed | Optional tag/status filters | Compact method catalog · `local` | [DataLens API Reference](https://yandex.cloud/ru/docs/datalens/openapi-ref/) |
| `dl_get_api_method_schema` | Return a bounded schema for one method | Before lifecycle planning or when input is unclear | Method name | Request fields, support policy, and doc URL · `local` | [Compiled API contracts](sources_en.md#public-api-contracts) |

## What is not a public tool

Raw RPC, granular route/template builders, standalone requirements helpers, and DQ/data-evidence compatibility tools may exist in code for tests and internal flows, but they are absent from normal `tools/list`. Do not put test-only environment flags in user configuration or build public instructions around hidden calls.
