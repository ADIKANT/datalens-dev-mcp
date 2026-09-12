# Authorized scope and delivery

The current request defines target, effect, and stopping point. A clear instruction to edit and deliver authorizes the necessary scoped reads, validation, save/readback and requested publish/readback. A compact plan informs the user; it does not add a pause. Resolve routine details from project context, fresh readback and schemas.

| Request | Continue through |
| --- | --- |
| Analyze; change nothing | Scoped read and report only |
| Save a draft; do not publish | Validate, save, saved readback |
| Update and publish this chart; preserve neighbors | Scoped update, save/readback, publish-from-saved, published readback |
| Delete these exact test charts | Dependency preview, preserve checks, exact scope, delete and readback |

`confirmed_delete` is the exact machine delete set matching the authorized scope and fresh preview, not proof of a fresh human click. Resolve a request to clean unused objects in a named workbook to a safe exact set through dependency reads. Revalidate changed previews; stop when changed scope or preservation conflicts cannot be resolved within the request. Failed or uncertain deletion stops the remaining objects; reconcile instead of blind retry or recreation. A list-only request and an explicit preserve instruction prohibit deletion.

Ask only when the target or effect remains ambiguous, the solution materially expands scope (including shared-source meaning, visibility or other objects), explicit constraints conflict, or a human login/secret/platform action is required. Unknown KPI polarity can be neutral; it does not require a questionnaire. A dashboard request does not authorize upstream production database writes, ACL changes, or unowned objects.

Native permission events remain host-controlled. Automatic reviewer `outcome=allow` is not a pending human response. Do not bypass a refusal, modify global configuration, or edit external skills. An external design process remains external; do not attribute its requirements to this plugin or introduce a second domain approval ceremony.

## Compact continuation

Use an existing project `AGENTS.md` or `CONTEXT.md` for a long handoff only when continuation needs it. Record the current scope; exact targets and branches; accepted decision and source version; verified results; uncertain operation IDs; remaining objects; and the conditions that require a fresh read. A current bounded request is authority for that scope; an old plan is context, not authority for a new write, publish, or cleanup.

After compaction, restore that short note and revalidate mutable facts selectively. A new revision or manual edit invalidates the affected object's saved state; a runtime change invalidates active-runtime evidence; a scope change invalidates the coverage boundary. Keep stable decisions and already verified independent objects. Treat each related source named in the current continuation request as a separate evidence obligation. Read the entity and properties that establish its current state; finding its identity or listing its children does not verify its metadata. If the response omits a required fact, use an addressed object read or report that fact as unresolved. A reconciled write does not close remaining source checks.

When the user narrows or cancels effects during a pending operation, stop dispatching newly cancelled writes. Cancellation of a UI call is not proof that a remote effect was cancelled or undone. Preserve the operation ID and receipt; reconcile an already dispatched effect using `dl_operation_get`, `dl_operation_reconcile` and exact readback before deciding what happened. Continue independent authorized reads. Do not clear receipts, repeat an unknown write after compaction, or claim rollback without evidence.

For multiple workbooks/projects, keep each project's exact root, workbook and object identities separate. Track every requested target from the start; a missing dependency in one does not block independent authorized work in the others. For a request covering six workbooks, account for all six before reporting the result. Maintain one row per requested target:

| Project / workbook / object | Required change | Evidence | Remaining |
| --- | --- | --- | --- |
| `project-a / workbook-a / chart-a` | Rename title | saved readback at current revision | publish only if requested |

Do not claim overall completion until every target has a row and no required remainder. Keep API save/readback, publish/readback, data proof, and Browser proof as separate evidence. A visible selector, Editor, or layout change needs relevant rendered verification; a metadata-only update does not require a full Browser tour.

Scale the final response to the request: a single rename needs the result and relevant readback, while a multi-project task needs per-target change, save/readback, requested publish/render and exact remainder. A status question or compaction continues the existing task unless the user changes it; keep accepted formulas and units rather than asking again.
