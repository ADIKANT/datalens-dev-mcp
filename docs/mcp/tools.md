# MCP Tools

The server exposes deterministic DataLens workflow tools. Routing and chart
selection belong to prompts, governance, configs, and schemas; tools execute or
plan specific operations.

## Standard Tool Surface

`tools/list` returns one standard DataLens surface for normal Codex work. The
surface includes runtime/auth status, API contract lookup, workbook/object
reads, complete dashboard snapshots, relation reads, project validation,
Advanced Editor runtime validation, source-error classification, object payload
validation, generic object-change planning, guarded dataset changes, dashboard
tab planning, safe apply, publish-from-saved planning, readback, validation
reports, manifest-backed project workflows, Delta v7 live maintenance
handoff, guarded RPC request compilation, and supplied-evidence source
availability orchestration.

Raw expert RPC and schema-only unimplemented dataset/calculated-field APIs are
not exposed by default. Granular chart authoring, DQ reconciliation, standalone
data-evidence helpers, and route/template builders remain callable through
internal compatibility tests only, but users do not select a tool surface
through env vars or local config. `initialize` reports the standard surface and
exposed tool count without secrets.

Hidden/internal compatibility calls require a test-only process marker:
`DATALENS_MCP_TEST_ONLY_REGISTRY=1` plus
`DATALENS_MCP_ALLOW_HIDDEN_TOOL_CALLS=1`. The hidden-call flag by itself is
ignored by normal runtime, and the normal launcher strips legacy profile and
hidden-call env vars unless the test-only marker is present. `dl_runtime_status`
reports this state under `runtime_env.tool_registry` and emits warnings for
ignored hidden-call flags, enabled test-only hidden calls, and legacy profile
env vars.

The standard surface also includes one bounded corpus reference tool,
`dl_reference`, and one bounded diagnostics tool, `dl_diagnose`. Diagnostics
cover SQL parser/lineage, aggregation grain, chart/dataset semantic graphs,
performance evidence ingestion, and optimization recommendations. Full SQL and
query evidence spill under ignored `artifacts/sql_performance/`; inline
responses carry hashes, counts, bounded findings, and artifact metadata.
Use `dl_reference` modes `chart_selection`, `renderer_contract`,
`negative_requirements`, `delivery_intent`, `api_contract`,
`current_docs_delta`, and `tool_selection` for workflow navigation instead of
reading long docs repeatedly. These modes return compact rules, exact next
tools, and artifact paths such as `docs/datalens/current_docs_reconciliation.md`
or `docs/datalens/api_contract_coverage.md` instead of dumping long knowledge
into chat.

Tool-selection and response-budget rules are documented in
`docs/mcp/tool_selection_policy.md` and
`docs/mcp/token_and_response_budget.md`.

## Default Tools

- `dl_get_local_config`
- `dl_runtime_status`
- `dl_auth_probe`
- `dl_validate_editor_runtime_contract`
- `dl_classify_source_error`
- `dl_diagnose`
- `dl_reference`
- `dl_validate_project`
- `dl_build_payload_plan`
- `dl_create_safe_apply_plan`
- `dl_execute_safe_apply`
- `dl_create_publish_from_saved_plan`
- `dl_readback_and_report`
- `dl_snapshot_dashboard`
- `dl_build_validation_evidence_report`
- `dl_list_workbooks`
- `dl_get_workbook_entries`
- `dl_get_entries_relations`
- `dl_read_object`
- `dl_plan_object_create`
- `dl_plan_object_update`
- `dl_validate_object`
- `dl_plan_guarded_dataset_update`
- `dl_plan_dashboard_tab_update`
- `dl_reconcile_partial_creates`
- `dl_list_api_methods`
- `dl_get_api_method_schema`
- `dl_detect_project_live_workflows`
- `dl_plan_project_manifest`
- `dl_plan_project_live_workflow`
- `dl_run_project_live_dry_run`
- `dl_run_project_live_apply`
- `dl_read_project_live_summary`
- `dl_run_live_maintenance_update`
- `dl_compile_guarded_rpc_request`
- `dl_build_dashboard_source_availability_matrix`
- `dl_validate_source_availability_consumers`
- `dl_plan_source_availability_patch`

`dl_create_publish_from_saved_plan` creates an internal publish operation only
from a saved-branch readback artifact. It rejects published or unknown branch
artifacts, records expected saved `revId`/`savedId`, and keeps published
readback as post-publish proof. Batch publish validation matches saved readback
by object id, never by list position.

Delivery intent is resolved separately from permission. Review requests stay
read-only, plan-only requests stay plan-only, draft/no-publish terms stay
save-only, and known-target implementation/fix/enhance requests proceed through
save, saved readback, publish from saved readback, and published readback when
Codex/tool approval and explicit guarded write gates are present. Production
planner responses include `delivery_intent_decision.state`,
`required_gates`, `satisfied_gates`, `next_action`, and `proof_path`. See
`docs/mcp/delivery_intent_policy.md`.

The standard surface is intentionally under the startup budget. Use
`dl_snapshot_dashboard` or `dl_read_object` instead of the granular
`dl_get_dashboard`, `dl_get_editor_chart`, `dl_get_wizard_chart`,
`dl_get_dataset`, and `dl_get_connection` compatibility helpers during normal
Codex work.

Delta v7 maintenance tools are the default narrow repair lane for known live
targets. Despite its compatibility name, `dl_run_live_maintenance_update`
does not execute DataLens writes or browser actions; it plans and validates
supplied guarded execution/runtime evidence and writes a
`datalens.delta_v7.live_maintenance_run.v1` artifact and refuses final `done`
without browser/runtime proof unless a non-rendering exemption is explicit.
`dl_compile_guarded_rpc_request` records method, object id, base revision,
payload hash, fresh-read source, readback branch, publish source, and changed
sections before an update enters safe apply. Source availability tools consume
supplied evidence only; they do not query Trino or DataLens by themselves.

Delta v8 makes that maintenance lane runtime-first by default. The normal mode
is `quick_visible_patch`: fresh-read the target object and touched tab, build a
minimal baseline diff, update existing object(s), save, publish, run targeted
browser/runtime smoke, and then hand off. `dataset_sql_patch`,
`source_availability_patch`, and `full_audit` are explicit modes. Responses
include `validation_budget` with skipped gates and reasons, plus
`runtime_first_status` values `runtime_passed`, `runtime_failed`,
`runtime_not_verified`, `blocked_before_write`, or
`structural_ok_runtime_not_checked`.

`validateDataset`, dry-run parity, and API readback parity are not completion
proof. `validateDataset` is a schema hint used only when dataset SQL/schema
changes. API readback is structural evidence. Browser/runtime smoke scans the
changed visible target for DataLens runtime markers and attempts sanitized
`More` / `Database response` / `Sent query` extraction when generic error cards
appear.

## Read And Discovery Tools

Normal Codex readback should use `dl_snapshot_dashboard`, `dl_read_object`,
`dl_get_workbook_entries`, and `dl_get_entries_relations`. The granular getters
below remain available only to compatibility tests and explicit internal calls
running with the test-only registry marker.

- `dl_probe_auth`
- `dl_list_workbooks`
- `dl_get_workbook_entries`
- `dl_get_dashboard`
- `dl_get_editor_chart`
- `dl_get_wizard_chart`
- `dl_get_dataset`
- `dl_get_connection`
- `dl_get_entries_relations`
- `dl_read_object`
- `dl_list_related_objects`
- `dl_get_dataset_schema`

`dl_get_workbook_entries`, `dl_get_dashboard`, `dl_get_editor_chart`,
`dl_get_wizard_chart`, `dl_get_dataset`, and `dl_get_connection` default to
`response_mode=summary`. `summary` and `structure` omit full hydrated payloads.
Explicit `response_mode=full` preserves compatibility for small responses.
`response_mode=artifact` always stores the sanitized full response under
`artifacts/runtime/mcp_runs/<run_id>/`. When a full response exceeds
`inline_char_budget`, the tool returns the compact summary plus artifact path,
serialized byte/character size, and SHA-256.

Migration note: callers that previously depended on default inline
`entry.data.sources`, `prepare`, dashboard items, or full workbook entry
hydration must request `response_mode=full` or consume the returned artifact.
The compact default is the intended MCP-facing path.

`dl_read_object` is the default high-level object reader. It resolves workbook
inventory types through a versioned registry instead of adding one tool per
type. The registry covers dashboards, Editor charts, Wizard charts including
`markup_wizard_node`, table nodes, d3/Gravity nodes, controls, Markdown nodes,
datasets, connections, QL charts including `graph_ql_node`, reports,
workbooks, collections/locations, and permissions. Dataset fields and
calculated fields are explicit embedded-in-dataset contracts rather than hidden
standalone reads.

## Object Lifecycle Plan Tools

These tools return guarded plans or honest unavailable-method specs. They do not
execute writes directly. Normal Codex work should prefer
`dl_plan_object_create`, `dl_plan_object_update`, `dl_validate_object`,
`dl_create_publish_from_saved_plan`, `dl_plan_guarded_dataset_update`, and
`dl_plan_dashboard_tab_update`; route-specific planners remain available for
compatibility tests and internal workflows running with the test-only marker.

- `dl_plan_object_create`
- `dl_plan_object_update`
- `dl_validate_object`
- `dl_plan_publish_from_saved` (compatibility-only; use `dl_create_publish_from_saved_plan` on the standard surface)
- `dl_create_editor_chart_plan`
- `dl_update_editor_chart_plan`
- `dl_create_wizard_chart_plan`
- `dl_update_wizard_chart_plan`
- `dl_create_dashboard_plan`
- `dl_update_dashboard_plan`
- `dl_create_connector_plan`
- `dl_update_connector_plan`
- `dl_create_dataset_plan`
- `dl_update_dataset_plan`
- `dl_plan_guarded_dataset_update`
- `dl_plan_dashboard_tab_update`
- `dl_create_dataset_field_plan`
- `dl_update_dataset_field_plan`
- `dl_create_calculated_field_plan`
- `dl_update_calculated_field_plan`
- `dl_save_object_plan`
- `dl_publish_object_plan`

The generic planners use named source adapters: `canonical_object_payload`,
`canonical_request_payload`, `rpc_readback_envelope`, `saved_entry`,
`published_entry`, `artifact_path`, and `project_manifest_reference`.
Ambiguous readback envelopes and summary-only reads are rejected before a
network call or safe-apply plan.

Standard chart creation uses `wizard_native` with one of the 16 canonical
visualization IDs. A fresh `getWizardChart` saved-branch seed of the same
visualization ID is preferred; otherwise the committed anonymized canonical
template is used. Safe apply preserves saved-readback visualization tokens,
including `column100p`, and blocks stale, guessed, wrong-branch, or mismatched
tokens before write. Unknown visualization IDs are blocked for create and may
be preserved on update only from fresh saved readback.

The same generic lifecycle planners handle `ql_chart` read/create/update.
Create/update require `route=ql_explicit`, direct-user-request approval
provenance, and an explicit payload or fresh saved QL seed. They never generate
QL from a general prompt. QL delete remains closed.

`dl_plan_guarded_dataset_update` models the full guarded dataset workflow:
fresh `getDataset`, `validateDataset`, optional approved `updateDataset`, then
saved readback. It preserves field GUIDs by default and blocks if affected chart
payloads still reference GUIDs that would disappear. It never plans publish as
part of the save/update step.

`dl_plan_dashboard_tab_update` appends or replaces one dashboard tab in a fresh
dashboard payload and keeps unrelated tabs plus existing metadata unchanged. It
does not force title or hint rewrites on unchanged legacy widgets.

## API And Local Helper Tools

- `dl_validate_object_payload`
- `dl_list_api_methods`
- `dl_get_api_method_schema`
- `dl_rpc_readonly`
- `dl_rpc_expert`
- `dl_build_workbook_source_resolution`
- `dl_build_selector_wiring_summary`
- `dl_build_runtime_verification_plan`
- `dl_run_wizard_to_js_plan`

`dl_rpc_readonly` and `dl_rpc_expert` are not exposed by the normal surface.
Use `dl_list_api_methods` and `dl_get_api_method_schema` for API contract
lookup. Raw expert RPC remains disabled unless explicitly enabled in the
runtime environment and is hidden from normal `tools/list`.

`dl_build_selector_wiring_summary` accepts hydrated dashboard entry objects,
not compact read summaries. The minimum shape is
`{"entryId": "...", "data": {"tabs": [...]}}`; callers using compact live
reads must pass an artifact-backed entry structure from a full/structure
readback before validating selector wiring.

## Runtime Diagnostics

- `dl_runtime_status` returns write/save/publish/expert flags, token presence,
  refresh-on-401 state, `yc` resolution status, org/API configuration, project
  root, local config path, and route-policy summary. It never returns token
  values.
- `dl_auth_probe` runs `getWorkbooksList` with `page=1` and `pageSize=1`, then
  returns `ok`, credential source location, env-file reload state,
  refresh-on-401 state, token-refresh availability, and a sanitized error if
  auth fails.
- `dl_validate_editor_runtime_contract` checks generated or hydrated Advanced
  Editor sections before save/publish. Findings include exact JSON path, line,
  rule, rule version, severity, and message.
- `dl_classify_source_error` classifies DataLens source/runtime errors into
  connection request refusal, authentication, SQL compilation/execution,
  runtime renderer, sanitizer, or unknown. Request-stage null-query failures
  are not SQL errors.

## Live Apply Hardening

Generated MCP payloads sanitize internal DataLens technical names before
create/update. Display fields such as titles, widget titles, hints, and
descriptions may stay human-readable. Technical names under `data.name`,
`meta.name`, `body.name`, `config.name`, `entry.name`, `chart.name`, and
serialized Editor metadata must use lowercase ASCII with `a-z`, `0-9`, `_`, or
`-`.

`dl_rpc_expert` does not validate names for read-only methods. For write
methods it preflights internal-name paths and returns `unsafe_internal_name`
with exact JSON paths and suggested sanitized values before any RPC call. The
expert override flag is `DATALENS_MCP_EXPERT_ALLOW_UNSAFE_INTERNAL_NAMES=1`
and defaults to false.

`dl_reconcile_partial_creates` reads workbook entries or accepts a supplied
`getWorkbookEntries` payload, matches planned objects by stable internal name,
display title, and type, and returns reuse/create/manual-review guidance. It
never deletes automatically.

`dl_detect_project_adapter` identifies `standard_bundle`,
`repo_live_workflow_manifest`, `dataset_update_workflow`,
`advanced_editor_project`, and `unknown_custom_layout`. Unknown or
manifest-free custom layouts return `adapter_required`/`manual_review` with
detected files, expected standard layout, adapter registry, evidence, and
recommended next actions.

Project live workflow tools make custom downstream project layouts explicit instead of
guessing writes from arbitrary scripts:

- `dl_detect_project_live_workflows` reads `.datalens-mcp.json`,
  `.datalens-mcp.yaml`, or `datalens-mcp.project.json`; without a manifest it
  returns `adapter_required` and a suggested manifest.
- `dl_plan_project_manifest` inspects the project, previews a proposed
  `.datalens-mcp.json`, and writes it only when `approved=true`.
- `dl_list_project_live_workflows` lists manifest-backed workflows, modes,
  affected objects, expected artifacts, evidence checks, and safety constraints.
- `dl_plan_project_live_workflow` returns the declared argv command, summary
  paths, workbook/dashboard ids, validated required env names, rejected env name
  declarations, affected objects, expected artifacts, evidence checks, safety
  constraints, expected object groups, retire lifecycle proof paths when
  `action=retire_legacy_objects`, and blocked reasons without execution.
- `dl_run_project_live_dry_run` executes only manifest-declared dry-run commands
  when `execute_now=true`; it uses a fresh allowlisted environment containing
  only execution basics (`PATH`, `HOME`, temp, and locale variables), validated
  manifest-required env names, and explicit DataLens injections
  (`DATALENS_ORG_ID`, API base/version, `DATALENS_YC_BINARY`, and IAM token env).
  Captured stdout/stderr is redacted with the shared redaction helper.
- `dl_run_project_live_apply` additionally requires approval, write/save flags,
  and manifest publish allowance when publish is requested. The same runner can
  execute `action=retire_legacy_objects`, but only after the retire manifest
  contract and pre-execution proofs pass.
- `dl_read_project_live_summary` parses JSON artifacts and returns changed
  object counts, dashboard/workbook ids, saved/published status, evidence
  paths, remaining drift, dashboard preflight, and SQL lint evidence.

Normal project-live actions block hidden destructive semantics in command
tokens and safety constraints, including `delete_legacy`, `delete-*`,
`deleteEditorChart`, `deleteDashboard`, permission mutations, move operations,
and `delete_move_permission_operations=true`. Explicit user-requested removal
uses the distinct `retire_legacy_objects` lifecycle with exact object ids/types,
workbook id, reason, user request quote or decision id, relation graph proof,
saved and published no-reference proof, dry-run retire plan, approval
provenance, execution summary, and post-retire readback.

Dashboard payload preflight is part of `dl_validate_project`, safe-apply
planning/execution, and project live workflow summary validation. It blocks
duplicate nested widget tab ids, duplicate widget/chart
ids, selector-control collisions, malformed nested tab ids, native title/hint
policy for new versus preserved legacy blocks, selector layout and
`impactTabsIds` violations, debug/service widgets, date-range selector
regressions, stale availability defaults, and unsafe internal technical names.

Safe-apply execution is artifact-first. Raw pre-write, write-result, and
readback envelopes are sanitized once and stored under
`artifacts/safe_apply/<run_id>/`. Inline action results contain action/method,
object id, executed/changed/status, revision ids, guard checks, concise errors,
and artifact path/size/hash metadata. `minimal` returns compact identity,
revision, status, counts, and hashes. `full` still stores full data as an
artifact and keeps inline output compact. `debug` adds a capped diagnostic
excerpt; oversized content still spills.

Editor SQL static lint is part of `dl_validate_project` and project live
workflow summary validation. It reports structured `error`/`warning`/`info`
issues for ClickHouse patterns known to fail live: tuple indexing,
`arrayZip` over independent regex arrays, unsafe quote escaping,
`NO_COMMON_TYPE`-prone `ifNull`/joins, correlated subqueries, unknown aliases,
aggregate-inside-scalar expressions, OR/pairwise joins, late filters,
production `SELECT *` probes, final rollup joins, raw JSON payload columns
visible by default, and availability default regressions.

SQL/performance semantic diagnostics are parser-backed rather than regex-only.
`dl_diagnose` modes include `sql`, `aggregation_grain`, `semantic_graph`,
`performance`, `optimization`, `synthetic_fleet_fixture`, and `acceptance`.
`dl_validate_project`, guarded dataset planning, and safe-apply preflight use
the same checks to block known Code 47, Code 48, and Code 184 incident shapes
before apply. Optimization output is advisory only and never mutates DataLens.

`dl_build_validation_evidence_report` separates static checks, safe-apply
plans, dry-run summaries, saved readback, published readback, dashboard layout
readback, Editor object readback, and direct SQL execution. When the curated
DataLens API catalog has no validated query execution method, it returns
`blocked_runtime_sql_execution` and recommends static lint, generated query
inspection, save/publish acceptance, object readback, and manual UI smoke.

Read-only data evidence tools provide a neutral abstraction over available
schema/data evidence providers:

- `dl_build_data_evidence_probe_plan` creates a table discovery, column list,
  bounded row count, bounded sample, CTE stage-count, link-direction, or
  freshness/availability probe plan. It is plan-only and rejects unsafe
  production probes such as `SELECT *`.
- `dl_record_data_evidence` stores sanitized evidence under the active project
  in `reports/data_evidence/` and updates `requirements/data_evidence.md`.
- `dl_evaluate_data_evidence` prevents false absence claims: truncated aggregate
  inventories return `INCONCLUSIVE_TRUNCATED` until targeted `table_discovery`
  evidence is supplied.

No sync or external cache maintenance tool is registered as a user-facing MCP tool.

## Support Status

| Surface | Status | Evidence |
| --- | --- | --- |
| Read/discovery tools | executable read-only | official read methods and safe client wrappers |
| Dashboard, Editor chart, Wizard chart, QL chart, dataset, connector write tools | guarded safe apply | official create/update methods exist; QL is explicit-only; execution requires approved safe apply, fresh read, save-first semantics, and readback |
| Dataset fields and calculated fields | unsupported standalone plan | official standalone methods are absent; represent inside dataset payloads |
| Requirements, blueprint, template, validation tools | offline executable | local deterministic workspace/config/template logic |
| QL chart methods | explicit-only guarded lifecycle | read is available; create/update require direct-request provenance and explicit payload or fresh saved seed; delete remains closed |

## Structured Error Categories

Object lifecycle tools return `ok: false` with one of these categories:

- `missing_input`
- `auth_failure`
- `unavailable_api_method`
- `datalens_validation_error`
- `unsupported_chart_type`
- `unsafe_sensitive_input`
- `unknown_runtime_error`

The stdio server also wraps unexpected tool exceptions into MCP `tools/call`
results with `isError: true` and the same structured `ok: false` error shape.
