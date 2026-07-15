# Safe Apply

Safe apply is a guarded write lane:

1. Validate local artifacts.
2. Build dry-run payloads.
3. Create a safe apply plan.
4. Review and approve the safe-apply tool execution or plan.
5. Enable writes with `DATALENS_MCP_ENABLE_WRITES=1`.
6. Fresh-read remote objects.
7. Preserve revisions and unknown fields.
8. Save first. Planning/review intents stop there; known-target implementation,
   fix, or enhance delivery continues through publish from saved readback when
   Codex/tool approval and explicit publish gates are present.
9. Read back according to `readback_mode` and write a deployment report.

## Readback Modes

- `none`: no live readback; requires a `readback_justification`.
- `minimal`: default; read dashboard plus the first supplied chart/object needed
  to prove linkage and saved shape.
- `full`: read all supplied objects.
- `debug`: same breadth as full, reserved for diagnostics.

Do not blindly read back both saved and published branches. Use saved readback
after save-mode writes. Published readback is explicit and reserved for critical
objects or debug/manual verification.

Saved and published readbacks use separate artifact names:

- `artifacts/readback/<target>.saved.latest.json`
- `artifacts/readback/<target>.published.latest.json`

The saved artifact is never overwritten by a published readback.

## Incident-Hardening Invariants

Every update action stores `desired_overlay` separately from its fresh
saved-branch readback. Immediately before writing, safe apply merges that
overlay onto the authoritative fresh object, preserves unknown live fields,
and restores request control/identity keys from the approved plan. Dashboard
`change_scope=content` also preserves fresh `x/y/w/h`; `layout` and `redesign`
require explicit `geometry_expectations` with exact `expected_old` and
`expected_new` coordinates.

Actions expose `transaction_group_id`, `change_scope`, `semantic_role`, and an
optional `shared_object_key`. A transaction group cannot partially publish:
all chart/dashboard save actions in the group need saved readback first.
Different semantic roles cannot point at the same live object unless they all
declare the same non-empty `shared_object_key`.

`ENTRY_IS_LOCKED` and `UNIQUE_VIOLATION` are reported as
`conflict_no_write` with distinct `remote_code` values. Lock errors may carry
`retry_after` and `lock_until`; uniqueness conflicts require reconciliation.
An unclassified exception after a write attempt is
`write_outcome_unknown` and never resumes automatically.

## Proof Levels

Every readback, deployment, validation, and safe-apply report labels proof
with one or more of these levels:

- `source_static`
- `installed_static`
- `live_read_only_api`
- `save_readback`
- `publish_readback`
- `browser_rendered`
- `controlled_live_write`

Do not state a generic `ok` without adjacent `proof_level`, `proof_levels`, or
`ok_proof_context`. API readback is not browser-render proof, saved readback is
not published readback, and static checks are not controlled live writes.

## Explicit Publish Lane

Publishing is a separate internal guarded operation. Build it with
`dl_create_publish_from_saved_plan` after saved readback exists. The publish
plan is blocked unless it references a saved-branch artifact and carries the
expected saved `revId` and `savedId`.

Delivery intent may request save-plus-publish, and the implementation/fix/enhance
request plus Codex/tool approval satisfies operator approval for the guarded
flow. It does not bypass runtime gates. Unknown targets, disabled writes,
missing tool approval, hidden destructive actions, or missing saved readback
remain blocked. Explicit user-requested legacy removal is outside generic safe
apply and must use the `retire_legacy_objects` project-live lifecycle.

The top-level safe-apply action mode remains `save` for executor compatibility.
Only the action payload may carry `mode: publish`, and only after the saved
artifact guard passes. Plans built from `branch=published` or an unknown branch
are rejected.

Reports must show saved readback before publish and published readback after
publish. If no object changed because partial-create reconciliation reused
existing objects, the plan returns `no_changed_actions` instead of success.

## Delta V6 Maintenance Defaults

Dashboard maintenance is existing-object-first. Before changing a known
dashboard, build a `baseline_diff_contract` from fresh live readback or an
operator-supplied read-only backup. The contract
must show preserved active objects, intended updates, appended objects, and any
layout or table/pivot feature regressions. Removing active widgets, replacing
working request-list/pivot objects, or losing links/actions/formatting blocks
the write unless the user explicitly authorized that scope.

Create actions require `creation_necessity_proof`. The proof must explain why
an existing object update is insufficient and must state that a cleanup report
is required if the create succeeds. Partial-create reconciliation remains
required before retrying failed creates.

Publish is not complete until changed tabs and changed objects pass
`runtime_publish_gate`. API readback, `validateDataset`, and saved/published
readback are necessary evidence, but they are not browser/runtime proof. If
browser verification is blocked by auth or tooling, final handoff status is
`runtime_not_verified`; do not report `done`.

Cleanup uses `object_cleanup_report`. New objects cannot be deleted, retired,
or cleaned up until saved and published active graphs prove they are absent.
An empty-body delete response is not enough; follow-up readback must verify
absence.

Live maintenance reports exactly one maximum proven `delivery_stage`:
`planned`, `saved`, `saved_runtime_passed`, `published`, or
`published_runtime_passed`. `publish_allowed` is true for a visible change only
after verified saved readback and a passed saved-branch runtime gate. Published
evidence supplied out of order cannot advance the stage. The deprecated
`runtime_gate_evidence` input is interpreted as published evidence and emits a
warning; new callers provide separate saved and published runtime evidence.

## Delta V7 Executable Maintenance Gates

Dashboard maintenance should enter `dl_run_live_maintenance_update` or the same
safe-apply contracts it orchestrates. The workflow writes a
`datalens.delta_v7.live_maintenance_run.v1` artifact and keeps API readback,
saved readback, published readback, browser runtime proof, metadata evidence,
and cleanup proof separate.

Safe-apply validation now blocks these maintenance regressions:

- create actions without `object_reuse_decision` and sufficient
  `creation_necessity_proof`;
- `Runtime Fix`, `V13`, `temp`, or similar object names without an explicit
  cleanup lifecycle;
- baseline diff contracts that remove active widgets or lose protected
  table/pivot/list features;
- supplied source availability matrices with conflicting consumers or
  publish-blocking `NO_TABLE`/`ERROR`/`UNKNOWN` states;
- high-fanout Editor selector/control sources without SQL-side filters and
  business-grain dedupe evidence;
- Wizard chart payloads whose field references do not resolve against dataset
  readback.

Final `done` is available only when the runtime gate passed or the change has
an explicit non-rendering exemption. Browser auth blocks, tooling timeouts, and
missing runtime artifacts produce `runtime_not_verified`; runtime markers such
as `ILLEGAL_AGGREGATION`, missing fields, unknown tables, 502, or Data fetching
error produce `blocked`.

## Delta V8 Runtime-First Default

Normal visible chart/tab maintenance uses the short runtime-first path:
fresh-read the target, diff only the touched tab/object, patch the existing
object, save, publish, run browser/runtime smoke, then hand off. The
`dl_run_live_maintenance_update` response includes `maintenance_mode`,
`validation_budget`, `runtime_smoke`, and `runtime_first_status`.

`validateDataset`, broad dry-runs, full workbook inventory, and API readback
parity are not acceptance gates. They are optional or structural evidence:
`validateDataset` is only a schema/compile hint when dataset SQL/schema changes,
and saved/published readback only proves structure. A changed visible chart/tab
is complete only when browser/runtime smoke passes or the handoff explicitly
reports `runtime_not_verified` / `runtime_failed`.

When a generic DataLens error card appears, the browser smoke should try to
open `More` and capture sanitized `Database response`, `Sent query`, or debug
details. Metadata-fetch remains read-only source evidence and Trino success is
not ClickHouse/DataLens runtime proof unless dialect equivalence is declared.
