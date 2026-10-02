# API compatibility snapshot, 2026-10-01

The supplied API v3 OpenAPI has SHA256
`ad17376165da0bd04dde559c5b19eb0a1aea2612c6f095f2f35fa5744ce3219d`.
Its 138 operations have 60 `read`, 24 `write`, 50 `privileged` and four absent
`x-mcp-scope` markers. The registry retains 42 selected operations and records
authorization scope separately from local effect and completion. The other 96
operations are coverage boundaries, including the new Lakehouse/cluster/storage/
job/SQL endpoints; they are not automatically tools or acceptance actions.
SDK remains pinned to 3.0.0.

| Contract | Current implementation and evidence boundary |
| --- | --- |
| Dashboard globals | Addressed `globalItems` and `data.group` children use the existing merge/save path; full tabs readback, revision drift and no-op checks remain. New native records are SDK-validated without serializing away unknown fields. |
| Editor response/create/update | Table/Gravity data: Meta, Params, Sources, Controls, Prepare, Config; optional Activities. Markdown/Advanced: Meta, Params, Sources, Controls, Prepare. Selector: Meta, Params, Sources, Controls; optional Activities. These response/create DTO requirements are not narrow-patch requirements. |
| Static draft | Existing complete-draft minima remain compatible. Newly documented tabs are optional at this layer. `supplied_tabs` validates only the exact provided fragments and reports those names; batch validation always uses complete-draft scope. Create builders retain their own provider-required defaults. |
| SDK carriers | Controls, Config and Markdown Sources use the existing generated carriers. Activities survives raw update/import for Table/Gravity/Selector; generated create builders have no setter and fail before dispatch rather than deleting the tab. Unchanged unknown tabs survive narrow updates. |
| Calendar input | Explicit Dataset `date_input` adapts observed native inputs; UTC calendar conversion and timezone-preserving ISO datetime are distinct. Native interval parsing delegates to Editor. Custom SQL retains its project owner. |
| Connection create | SDK parses id-only, null operation and object operation responses. Keep the returned id before readback. A non-null operation has no generic documented poll in the selected API and remains incomplete; even an apparent `done` key is not a verified completion contract. Do not replay create. |
| HTML audit | `getHtmlPage` documents optional `x-dl-audit-mode: true`. Documented only until an authorized Page proves the result; no arbitrary header passthrough. `data` is arbitrary and does not guarantee HTML source. |
| HTML preview | `getHtmlPagePreviewUrl` is documented but unregistered: `{entryId, branch?, revId?, lang?, theme?}`; branch defaults to published, lang is ru/en, theme light/dark/light-hc/dark-hc/system. A future verified read must select saved/published/revision explicitly. Temporary authenticated preview URLs do not publish or create public shares and must not enter durable logs/Git. |
| HTML authoring | Source readback remains unverified; no Page content writer is enabled. Existing revision publication is separate from source authoring. |
| Method lookup | `dl_method_schema` describes provider methods. Passing an MCP tool name returns its exact tools/list schema location and compact fields, without a full method catalogue or automatic write. `dl_object_diff` has no expected_revision; writes use changes[].expected_revision. |

Primary source references: [Editor tabs](https://yandex.cloud/en/docs/datalens/charts/editor/tabs)
and [Editor methods](https://yandex.cloud/en/docs/datalens/charts/editor/methods).
The supplied OpenAPI snapshot is the versioned source for endpoint metadata;
local SDK transport checks are not native execution or Browser evidence.

Use the [composition example](../../skills/datalens-dashboard/references/composition.md)
and [calendar input contract](../../skills/datalens-editor/references/editor-authoring.md#native-calendar-inputs).
Check only affected controls, source families and widgets; preserve source needs
3/2/1, metric denominators, distinct windows, weights, ties, actual zeros and manual
layout. Smaller response projection does not prove a smaller physical scan.

## Acceptance evidence

This table separates transport/static checks from a controlled provider canary.
Private snapshots, object identities, receipts and browser images remain outside
the repository. An unavailable scenario is not promoted to a pass by local tests.

| Case | Evidence and remaining boundary |
| --- | --- |
| D-UC01 | Recorded fail-before reproduced; compact and generic local results agree. Fresh topology copy: exactly two global defaults added, saved and separately published, complete neighboring data preserved; repeat is no-op. |
| D-UC02 | Local/SDK checks cover namespace ambiguity, absent IDs, group children, exact values and concurrent revision drift. A provider group-add canary returned HTTP 500; receipt remains uncertain after read-only reconciliation and was not replayed. Group live completion is unresolved. |
| D-UC03 | Native range control emits ISO start/end-of-day values. Synthetic fixed rows render 7 without period, 6 with period, 5 with a selected category, and 6 after clearing only the date. Neighbor tab has no unintended global control. Business-source end-to-end rendering remains blocked by chart view rights on the copied references; synthetic Prepare filtering is not proof of that query. |
| D-UC04 | Four recorded table drafts pass unchanged static validation with source hashes preserved. SDK transport carries Controls and a native canary renders the recorded empty Controls export. Full private table business results were not republished. |
| D-UC05 | Documented minimal drafts and actual SDK transport exercise the subtype/update matrix; generated create Activities remains a precise pre-dispatch gap. Native execution of every Activities subtype was not observed. |
| D-UC06 | Wrong-level method lookup and diff revision input return compact guidance; old provider lookups remain covered. |
| D-UC07 | Actual SDK parsing covers id-only, null and opaque pending operations, known ID/readback failure and no create replay. Native pending connection provisioning is NOT_OBSERVED. |
| D-UC08 | No authorized HTML Page was available. Audit/preview remain documented-only, with live verification BLOCKED; content authoring remains unsupported. |
| D-UC09 | All 42 selected methods match the supplied snapshot; 138 operation marker counts are recorded separately from effects. No additional provisioning tools were registered. |
| D-UC10 | Existing source/runtime/semantic checks preserve active Sources 3/2/1 and metric behavior. Historical project parity remains reference evidence; no new production query/physical scan claim is made. |
| D-UC11 | Existing batch/transport/admission tests cover partial success, Retry-After and unknown/no-replay recovery. Canary admission failure proved zero dispatch; later confirmed rejection resumed once. Provider HTTP 500 remains unknown. New live 429 is NOT_OBSERVED. |
| D-UC12 | Native calendar render and affected layout checked. Full offline acceptance passes; exact merged installation and active host identity are separate delivery gates, recorded with private release evidence. |
