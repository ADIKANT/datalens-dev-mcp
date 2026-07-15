# MCP Response Contracts

Source trace: MCP object lifecycle tools, API catalog, safe apply policy, requirements workflow, chart parameter matrix, Wizard template registry, and prompt-pack response examples.

All responses must be generic and sanitized: no tokens, auth headers, private key material, env-file contents, or sensitive live connection values.

## Requirements Ingestion

Input:

```json
{"markdown_text": "# Ops Dashboard\n- Audience users: operators\n- Metric KPI: order_count\n- Selector filter control: region", "source_name": "REQ-001"}
```

Return:

- `ok`
- target requirements file
- extracted section counts
- selected dashboard blueprint
- critical questions for missing audience/action/KPI/source/quality evidence

## Dashboard Planning

Return business-readable purpose, dashboard type, confidence, reason, job-to-be-done, recommended layout, draft chart plan, native title/hint policy, selectors, relations, and critical questions.

## Wizard Chart Create Plan

Return:

- `route=wizard_native`
- `visualization_id` and semantic family
- `selection_origin` and `selection_reason`
- template provenance and `source_kind=canonical_template|saved_seed`
- sanitized seed binding/hash when a seed is used
- dataset reference
- field bindings, roles, options, and validation report
- `method=createWizardChart`
- compiled payload with location XOR (`key` or `workbookId + name`)
- `safe_apply_required=true`
- `execute_now=false`

`wizard_map_native` is accepted as a `geolayer` compatibility alias. Unknown
visualization IDs, stale/wrong-branch seeds, and mismatched seed visualization
IDs return a blocking validation report.

## QL Explicit Plan

Return `route=ql_explicit`, `selection_origin=explicit_user_request`, bounded
approval provenance, explicit payload or fresh saved seed provenance, guarded
create/update method, and `execute_now=false`. Without direct-request evidence
or a payload/seed, return a blocking policy error. No general prompt-to-QL
generation is performed and QL delete is unavailable.

## Advanced Editor Chart Create Plan

Return:

- route and family from `config/datalens_chart_param_matrix.json`
- `chart_decision_record` with business question, analytical task, selected
  family/route, rejected families, negative requirements, and confidence
- `renderer_visual_spec` with style tokens, encoding, native title/hint policy,
  runtime constraints, and table/KPI formatting contracts
- source template directory
- generated Editor tabs
- `parameter_spec`
- `Editor.wrapFn` and `Editor.generateHtml` validation status
- native title/hint metadata in relation artifacts
- `execute_now=false`

## Dataset, Connector, And Field Plan

Return official method when supported, schema path, payload keys, sensitive-key validation, safe-apply requirement, and execution status. Standalone dataset-field and calculated-field operations return `ok=false`, `implemented=false`, and `error.category=unavailable_api_method`.

## Selector Relation Plan

Return selector id, param, `labelPlacement=left`, percentage width, row total `96%`, target widgets/charts, source field validation, dashboard filters, and relation artifact path.

## Safe-Apply Save/Publish/Readback Plan

Save plan returns mode `save`, fresh-read requirement, revision preservation,
readback mode, payload path, and deployment report path. Publish is a separate
internal operation built from saved readback evidence; for known-target
implementation, fix, or enhance requests, Codex/tool approval plus the guarded
write/save/publish gates is sufficient to proceed without a second literal chat
phrase.

Each safe-apply action binds `transaction_group_id`, `change_scope`,
`desired_overlay`, `semantic_role`, and optional `shared_object_key`.
Execution binds the overlay SHA-256 and merges it over fresh saved readback;
unknown live fields remain intact. Content-only dashboard changes preserve
fresh geometry, while layout/redesign changes carry exact old/new geometry.
Group publish stays false until every chart/dashboard save in the group has a
saved readback. Conflict results distinguish `ENTRY_IS_LOCKED`,
`UNIQUE_VIOLATION`, and `write_outcome_unknown` resume policies.

Production planners and executors that resolve delivery intent return
`delivery_intent_decision` with `state`, `reason`, `required_gates`,
`satisfied_gates`, `next_action`, and `proof_path`.

Execution returns compact aggregate and per-action status only. Aggregate
fields include `executed`, `status=blocked|completed|partial|failed`,
`proof_level`, `proof_levels`,
`completed_action_count`, `failed_action_index`, rollback artifact metadata,
and readback artifact metadata. Raw pre-write, write-result, and readback
envelopes are sanitized and written once to
`artifacts/safe_apply/<run_id>/`; inline fields include action, method, object
id, executed/changed/status, pre-write/write/readback revision ids,
guard/preflight checks, concise error, and artifact path, size, and SHA-256.

Readback mode semantics:

- `none`: no readback, requires justification.
- `minimal`: identity, revisions, status, counts, and hashes inline.
- `full`: full data is stored as an artifact; inline output stays compact.
- `debug`: diagnostic inline excerpt is capped; oversized content still spills.

Batch publish/readback matching is by object id, never by list position.
Reports and readback artifacts must label proof levels explicitly. The allowed
taxonomy is `source_static`, `installed_static`, `live_read_only_api`,
`save_readback`, `publish_readback`, `browser_rendered`, and
`controlled_live_write`. A report-level `ok` is only meaningful with
`ok_proof_context`, `proof_level`, or `proof_levels`; do not treat generic
`ok=true` as proof without that context. Saved readback and published readback
remain separate proof classes.

Delta v6 dashboard maintenance responses add these artifact contracts when the
workflow changes existing dashboard runtime objects:

- `baseline_diff_contract`: schema
  `datalens.baseline-diff-contract.delta-v6`; includes `baseline_source`,
  preserved/updated/appended/blocked object rows, tab presence, unexpected
  layout diffs, and `blocked_reasons`.
- `creation_necessity_proof`: required on create actions; explains why update
  was insufficient and marks cleanup reporting as required if creation occurs.
- `runtime_publish_gate`: schema `datalens.runtime-publish-gate.delta-v6`;
  includes changed object ids, checked browser/runtime error markers, visible
  assertions, selector statuses, proof artifacts, and status
  `passed|failed|blocked|not_run`.
- `object_cleanup_report`: schema
  `datalens.object-cleanup-report.delta-v6`; classifies created objects
  against saved and published active graphs before any cleanup action.
- `final_handoff_contract`: schema `datalens.final-handoff.delta-v6`; final
  status is only `done`, `runtime_not_verified`, `blocked`, or `rolled_back`.
  `done` requires a passed runtime gate for changed runtime objects.

Published browser/runtime failures are blocking evidence, not cosmetic notes.
Examples include field-not-found errors, SQL alias/runtime field mismatches,
selector load failures, and 502 responses. If auth or tooling prevents the
runtime gate from running, return `runtime_not_verified` instead of `done`.

Delta v7 maintenance responses add these executable contracts:

- `live_maintenance_run`: schema
  `datalens.delta_v7.live_maintenance_run.v1`; records target ids, intent,
  phase statuses, blocked reasons, separate saved/published runtime gates,
  `publish_allowed`, the exact five-value `delivery_stage`, cleanup plan, and
  final handoff artifact path.
- `guarded_rpc_request`: schema
  `datalens.delta_v7.guarded_rpc_request.v1`; records method, object type/id,
  branch mode, base revision, payload SHA-256, fresh-read artifact, readback
  expectation, publish source artifact, and changed sections.
- `runtime_gate_evidence`: schema
  `datalens.delta_v7.runtime_gate_evidence.v1`; marker counts include Data
  fetching error, Unknown field, non-existent field, DB exceptions,
  ILLEGAL_AGGREGATION, missing DataLens fields/columns, 502, and UNKNOWN_TABLE.
- `source_availability_consumer_matrix`: schema
  `datalens.delta_v7.source_availability_consumer_matrix.v1`; distinguishes
  `OK`, `NO_DATA`, `NO_TABLE`, `ERROR`, and `UNKNOWN` for every
  source/environment/consumer row. Conflicting consumers block publish.
- `editor_source_budget_evidence`: schema
  `datalens.delta_v7.editor_source_budget_evidence.v1`; selector/control or
  dashboard-critical high-fanout sources block publish unless SQL-side
  filtering and business-grain dedupe evidence are supplied.
- `wizard_field_binding_report`: schema
  `datalens.delta_v7.wizard_field_binding_report.v1`; validates Wizard field
  references against dataset readback, chart-local fields, labels, formulas,
  `datasetsPartialFields`, raw schema aliases, and grouped-bar modeling.
- `object_reuse_decision`: schema
  `datalens.delta_v7.object_reuse_decision.v1`; required before create actions
  can pass safe-apply validation.
- `final_maintenance_handoff`: schema
  `datalens.delta_v7.final_maintenance_handoff.v1`; final status is only
  `done`, `runtime_not_verified`, `blocked`, or `rolled_back`.

Delta v8 maintenance responses add runtime-first fields without replacing the
v7 artifact names:

- `runtime_first_run`: schema `datalens.delta_v8.runtime_first_run.v1`;
  records target, mode, `validation_budget`, `runtime_smoke`, artifacts, and
  `runtime_first_status`.
- `browser_runtime_smoke`: schema
  `datalens.delta_v8.browser_runtime_smoke.v1`; records the changed tab/chart
  scope, checked runtime markers, blocking markers found, console/DOM error
  counts, screenshots, and sanitized extracted error details.
- `sql_runtime_reality_check`: schema
  `datalens.delta_v8.sql_runtime_reality_check.v1`; records dialect, target
  execution engine, validators used, dialect equivalence, risk patterns, and
  whether a runtime probe is still required.
- `source_availability_runtime_matrix`: schema
  `datalens.delta_v8.source_availability_runtime_matrix.v1`; keeps Source
  Tables, Data Health, Overview, Data Quality, selectors, and controls on one
  availability truth.

The acceptance hierarchy is browser/runtime smoke, extracted runtime error
details, targeted source evidence, saved/published readback for structure, and
`validateDataset` only as a schema hint. `validateDataset=ok`, dry-run success,
or API readback parity cannot produce final completion for a changed visible
chart/tab without runtime smoke.

## Project Live Summary

`dl_read_project_live_summary` accepts explicit `action` and `summary_path`
selection. Summary responses return `action`, `publish_requested`,
`summary_path`, checked artifact counts, missing declared artifacts, and
blocking issues. Declared non-optional dashboard preflight, static SQL lint,
semantic SQL, readback, or target evidence checks fail with `zero_coverage`
when no matching artifact is checked.

For `action=retire_legacy_objects`, the plan response must include a
`retire_lifecycle` object with exact object ids/types, workbook id, reason,
user request quote or decision id, allowed lifecycle states, and declared proof
paths. The summary response treats relation graph proof, saved no-reference
proof, published no-reference proof, dry-run retire plan, approval provenance,
execution summary, and post-retire readback as required evidence. Saved and
published no-reference proof artifacts must explicitly assert zero references.

## Compact Read Responses

Dashboard summary returns identity/revisions, workbook, title, branch, tab ids
and titles, item/control/widget/link counts, selector impact wiring, linked
object ids/counts, and stable hash/size metadata. It does not inline
`entry.data`.

Editor chart summary returns identity/revisions, workbook, type, title,
annotation, link ids/count, data section names, each section length, and
SHA-256. It does not inline `sources`, `prepare`, `controls`, `config`, or
full code.

Workbook entries, Wizard chart, dataset, and connection summaries return
compact identity/type/title rows plus size/hash metadata and omit unrelated
hydrated fields.

`dl_read_object` returns the same compact-by-default shape for every registry
object: `ok`, object id/type, attempted method, branch, versioned contract
metadata, summary, and optional artifact metadata. Structured failures include
`object_id`, `attempted_method`, `error.category`, bounded message, and bounded
remediation. Unsupported or embedded-only types are not hidden; they return
`unsupported_type` or `unavailable_api_method` with the registry contract or
supported parent-read path.

## Runtime Contract Diagnostics

`dl_validate_editor_runtime_contract` validates generated or hydrated Advanced
Editor sections against rule version
`2026-06-25.datalens_advanced_editor_runtime.v2`. Findings include severity,
rule, exact JSON path, line, source, rule version, and message. Known sanitizer
failures such as custom `data-*`, inline `<script>`, SVG marker tags and
marker attributes, unsupported `rel`, duplicate inline title/hint rendering,
forbidden runtime calls, decorative CSS, custom HTML table bars, and non-string
selector option values block safe apply before write. Audited overrides apply
only to unknown warnings, never known forbidden errors.

`dl_classify_source_error` separates connection/request-stage refusal,
authentication, SQL compilation/execution, runtime renderer, and sanitizer
failures. `stage=request` with `query=null` is not classified as an SQL error.

Use `response_mode=full` for explicit compatibility access or
`response_mode=artifact` to force artifact-backed full data.

## SQL And Performance Diagnostics

`dl_diagnose` returns compact inline findings and writes full evidence under
`artifacts/sql_performance/`. Inline SQL diagnostics include source SHA-256,
parse status, bounded findings with source offset/line/column/CTE/identifier,
and remediation. They do not inline full SQL text.

Aggregation/grain diagnostics report physical source grain, dataset output
grain, dataset field aggregation status, chart aggregation compatibility,
blockers, and remediation options. The optimizer returns recommendations only:
confidence, evidence source, exact-versus-approximate semantics, selector/date
compatibility, parity scenarios, rollback plan, and stop conditions. It does
not automatically mutate formulas, datasets, charts, or dashboards.

Performance diagnostics separate `api_observed`, `browser_inspector`, `trino`,
and `static_estimate` timings. Missing Inspector evidence is reported as
`timing_unavailable`; callers may import signed browser Inspector/HAR evidence
instead of relying on fabricated render timings.

High-fanout selector and large-table sources must include source-budget rows
with physical rows before filtering, business-grain rows after filtering, SQL
filter pushdown status, and business-grain dedupe status. Selector sources
whose fanout exceeds the budget block publish until filtering and dedupe happen
at SQL/source grain before Editor/browser fetch.

Source availability matrices distinguish `NO TABLE`, `NO DATA`, `ERROR`, and
`OK`. `NO TABLE` means the table is physically absent or statically unsupported;
`NO DATA` means the table exists but returns zero rows; `ERROR` is a query or
runtime failure. Runtime selector parameters cannot make a statically
unsupported source available.

## Reference Responses

`dl_reference` returns bounded source-traced records for modes `search`,
`authoring_guidance`, `recipe`, `formula`, `visualization`, `error`,
`capability`, `source_trace`, `chart_selection`, `renderer_contract`,
`datalens_editor_runtime`, `dashboard_system_type`, `negative_requirements`,
`delivery_intent`, `api_contract`, `current_docs_delta`, and `tool_selection`.
Every response includes `summary`, at most five `rules`, `exact_next_tools`,
`artifact_paths`, `reference_version`, `reference_date`, and `response_chars`.
Responses distinguish official documentation, observed runtime overrides, local
policy, implementation status, and distilled local governance. Source-traced
records include source URL, mirror path, anchor or chunk id when available, and
SHA-256. Oversized evidence spills to a local artifact instead of inlining full
source pages.

For `mode=current_docs_delta`, `artifact_paths` must include
`config/datalens_docs_feature_policy.json` and
`docs/datalens/current_docs_reconciliation.md`. For `mode=api_contract`, it
must include `config/datalens_api_operation_policy.json` and
`docs/datalens/api_contract_coverage.md`. These modes point operators to the
current docs/API reconciliation artifacts and exact next tools; they do not
dump long documentation into chat.

## Unsupported Method

Return `ok=false`, `implemented=false`, `error.category=unavailable_api_method`, the missing official method or schema-only status, and a supported alternative when one exists. Documented but closed routes use the literal `reference_only` policy status.

## Missing Input Fallback

Return a concise question tied to the missing field:

```json
{"status": "blocked_question", "question": "Which business question, metric, dimension/date field, and intended action should this chart support?"}
```

## Missing Credentials

Return `BLOCKED_LIVE_CREDENTIALS`, required env vars, and exact retry tool/method. Do not print secret values, token lengths, or token prefixes.

## Validation Failure

Return compact field/route/schema issues without token, auth header, or credential values.
Empty fixtures cannot produce a pass. Validation evidence fails when dashboard
payload preflight, static SQL lint, or semantic SQL checks report zero checked
paths or zero checked SQL.
