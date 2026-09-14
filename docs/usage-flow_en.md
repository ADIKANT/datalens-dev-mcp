# Direct DataLens operations

[Русский](usage-flow.md) · [Connect](codex_setup_en.md) · [Tools](tools_en.md)

Work from the exact dashboard project/subproject using the installed domain skill. Start with the requested object and reuse the known installation and runtime. Use `dl_server_info` for an unknown or changed runtime and `dl_auth_check` for an access probe. Read addressed SDK/reference sections only for an unknown contract or changed version.

| Task | Short route and sufficient verification |
| --- | --- |
| Metadata question | `dl_object_get` with summary/projection of needed fields → answer. Inventory and relations only when needed |
| Description or other narrow metadata edit | Full saved target → narrow patch through `dl_object_update` → saved readback in the operation result |
| Dataset field, formula, filter or source | [Dataset/Wizard](../skills/datalens-dataset-wizard/SKILL.md): preserve unknown fields and both revisions; applicable validation/preview → update/readback |
| One Editor tab | [Editor](../skills/datalens-editor/SKILL.md): preserve other tabs/aliases → validate changed source → update/readback → Browser for changed behavior or appearance |
| Dashboard filter/layout/composition | [Dashboard](../skills/datalens-dashboard/SKILL.md): read affected bindings/dependencies, preserve neighbors → validate/update/readback → check filter/geometry in Browser |
| Shared renderer | Change its owning source project within authorized scope; check the affected family and consumers. Do not apply this cycle to a single metadata edit |

Prefer Wizard for a new standard chart; preserve existing technology. For registered Editor recipes use `dl_authoring_defaults` → `dl_compile_recipe`; pass the compact `draft_reference` to validation/create, or its artifact path with exact identity/revision to update. Do not echo packaged JavaScript. For new composition validate the batch through `dl_editor_validate`, create dependencies in order and carry `visual_contract` into item `presentation`.

`dl_object_diff` is optional: it reads one target and returns changed paths/values. `include_proposed=true` adds the full proposed snapshot when needed. Full MCP data lives in `structuredContent`; object/snapshot/diff text is a short summary. Do not run a workbook graph scan after a narrow update.

Operation results contain identity, status, changed fields, revision and the readback boundary. `no_change` means the intent matched fresh saved state without an external write. Full redacted details are available through `detail_reference` with `dl_operation_get(include_detail=true)`. Read again for an unresolved detail or drift, not automatically to retrieve an already verified revision.

Authorization, save-only, publication and unknown-write rules live in [authorized scope and delivery](../skills/datalens-dashboard/references/authorized-scope.md). Requested publication uses `dl_object_publish` from a saved revision and verifies published readback. Dataset/Connection have no separate publish branch. An uncertain result requires `dl_operation_reconcile`, not another write.

JSON/static validation proves a local contract, not metric meaning or rendering. Use data preview for changed data and read-only Browser for changed appearance/behavior, after API and applicable data checks. Metadata-only, read-only and packaging work need no visual cycle. Read only the applicable [visualization decisions](../skills/datalens-dashboard/references/decision-quality.md) section for KPI, time, scales or composition.

Backup, scoped cleanup and standalone HTML Page work belong to [Maintenance](../skills/datalens-maintenance/SKILL.md). Page content create/update stays unavailable without proven content readback. Package smoke and fake-HTTP scenarios are local contract guards; an actually completed DataLens task needs an observed result on an authorized object. Report unavailable live verification separately.
