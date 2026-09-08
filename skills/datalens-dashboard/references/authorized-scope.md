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
