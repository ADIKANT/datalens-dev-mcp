# Safe Apply

[Русский](safe-apply.md) · **English** · [Workflows](usage-flow_en.md) · [Safety](local-only-safety-model_en.md)

Safe Apply connects the original user request, exact target, current revision, DataLens API request, and readback results.

## Sequence

1. Read the target object and relations.
2. Check object type, ID, and saved revision.
3. Build the change over current state.
4. Validate the payload and project materials.
5. Create a plan with normalized mode, target lock, and SHA-256 of the original request.
6. Re-check write/save/publish settings immediately before writing.
7. Save.
8. Read saved state and verify the result.
9. If the task requires publishing, first build and validate publish actions
   for the complete group from saved readbacks.
10. Execute the validated publish group and read every published object.
11. Verify visible changes in the DataLens UI.

An explicit create, fix, update, enhance, or redesign request for a known object authorizes ordinary save and publish within this sequence. The server does not ask again before those steps.

## Request modes

| Wording | Result |
| --- | --- |
| audit, review, diagnose, inspect | Read and report |
| plan-only, dry-run | Plan without writing |
| save-only, no-publish, draft | Save and saved readback |
| create, fix, update, enhance, redesign | Save, saved readback, publish-from-saved, published readback |
| manifest action `retire_legacy_objects` | Deletion plan and separate confirmation |

The mode is stored in the plan and inherited by publish-from-saved. Publishing does not run when the original request was `save-only` or `no-publish`.

## Plan and target lock

`dl_create_safe_apply_plan` writes a plan inside the project root. It records:

- normalized operation mode;
- SHA-256 of the original user request;
- exact target type and ID;
- expected revision and branch;
- changed fields and desired overlay;
- API methods and expected readbacks;
- validation results and blockers.

`dl_execute_safe_apply` receives `plan_path`. Before RPC, it reads the target again, verifies the target lock, and overlays the requested change on current state. IDs, revision, chart technology, and unknown fields are preserved.

## Hard-off switches

- `DATALENS_MCP_ENABLE_WRITES=0` blocks all write requests.
- `DATALENS_MCP_LIVE_ALLOW_SAVE=0` blocks save.
- `DATALENS_MCP_LIVE_ALLOW_PUBLISH=0` allows a permitted save and ends as `saved_not_published`.

The server checks these settings immediately before the corresponding RPC. They take precedence over request text and local configuration.

## Readback

`readback_mode` values:

- `minimal` — the target and data needed to verify the change;
- `full` — all supplied related objects;
- `debug` — full diagnostic data;
- `none` — only for a no-live-write operation with an explanation.

Saved and published state are read separately. Their reports and artifacts use different names and do not overwrite each other.

## Publish from saved state

Normal updates build publishing from saved readbacks inside
`dl_execute_safe_apply`. Before the first publish RPC, the server validates
every object's saved artifact and the complete action set. A preparation
failure for one object blocks publishing for the whole group.

`dl_create_publish_from_saved_plan` is an explicit resume tool. It receives
saved readback, object type and ID, plus an optional `target_workbook_id`. The
plan records `revId`, `savedId`, and the saved-result path. Publishing is
blocked when saved readback is missing, stale, or belongs to another target.

After publishing, `dl_readback_and_report` reads published state and creates a deployment report. For a UI change, API readback verifies structure and the DataLens check verifies rendering.

## Updating an existing object

For updates, desired changes remain separate from the current object. Immediately before writing, the server overlays them on fresh saved state. A dashboard content change preserves untouched widget coordinates; a layout change must declare expected geometry.

A related action group is fully saved and verified first. Publishing begins only after every affected object has successful saved readback.

### Semantic date-range merge

`dl_create_safe_apply_plan` accepts
`maintenance_contract.kind=date_range_selector_merge` for a bounded update to
an existing Editor selector and its dashboard mount. The compiler replaces
exactly two static `datepicker` controls with one `range-datepicker`, changes
only two string array values in Params, synchronizes dashboard defaults, and
preserves other controls, layout, technology, and unknown fields.

The plan includes a sorted selector+dashboard `target_objects` lock,
`workflow_metrics` with a 14-RPC limit, and required `runtime_smoke`. The
maintenance result remains `runtime_smoke_required` until that browser check
is completed.

## Conflicts and unknown outcomes

- Object locks and uniqueness failures return a conflict without another write.
- A stale revision requires a new read and plan.
- An error after sending a write without a confirmed result returns `write_outcome_unknown`; current state is read before continuing.
- A retry after an interrupted create begins with `dl_reconcile_partial_creates` to avoid duplicates.

## Delete a complete object

Arbitrary whole-object deletion is not part of the standard lifecycle surface.
The only supported path is a project-manifest `retire_legacy_objects` action.
The first call returns `delete_confirmation_required`, exact IDs, relations,
and the plan hash. Execution requires another call with `confirm_delete=true`
for that same plan. Any target or plan change invalidates the confirmation.
Whole-object QL deletion is unsupported.

Removing a legend, filter, column, tab, or widget inside an object is an update and follows the normal write safeguards.
