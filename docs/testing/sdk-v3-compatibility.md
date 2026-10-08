# SDK 3.2.0 compatibility

This change retains the typed public operations, mutation receipts, request digests,
process claims, fresh saved-state merge, adapter preflight, and independent readback.
The SDK migration is separate from package versioning. No runtime SDK auto-upgrade
or generic write gateway is introduced.

## Pinned upstream and installation

The dependency is `datalens-sdk==3.2.0`, from the official
[datalens-tech/datalens-sdk release](https://github.com/datalens-tech/datalens-sdk/releases/tag/v3.2.0).
The stable release was checked on 2026-10-08 and resolves to commit
`f173ae3eec6d62db924ab03afe7773896a238f15` (annotated tag object
`730db4107785c1f7e9b9a8563d1da3a5bfbb792a`). PyPI and GitHub artifacts agree:
wheel SHA256 `935bc0132a2211cba86ee28ca1d9b7f030df6fdc6c961b0d42ceb24bee27bba3`,
sdist SHA256 `6163d429e13d8d164fe94fd984aaeb3c0914348a0c01df0f5979f22b5d88faa2`.
The adapter uses installed official carriers; no upstream tree or specification
is vendored. The SDK remains Apache-2.0.

### Migration from 3.0 through 3.1 to 3.2

| Used path | Verified target contract and decision |
| --- | --- |
| Dashboard create/manual controls | Converter unchanged between installed 3.0 and 3.2; exact HTTP bytes and manual input without `fieldType` remain tested; create has no save/publish mode |
| Dashboard update/publish | 3.1 adds `.mode()`; existing explicit `execute(publish=False)` remains supported for save; publish retains `publish_revision` and exact revision readback |
| Wizard | 3.1 raw replacement stops sending `revId` during save; remove the plugin's copied-handle workaround and retain the full-state/no-revision wire regression |
| Editor | 3.1 separates read/create/update carriers and adds `publish_revision`; use it for exact saved-revision publication and require that same revision on readback/reconcile |
| QL | Supported raw save/publish still sends full content; no exact-revision publication method is exposed; do not claim one |
| Dataset | 3.2 raw replacement still drops `dataset.revision_id`; retain the narrow adapter and both independent revision guards, including explicit observed null |
| Revision history | New resource-level pager is available; existing bounded public `getRevisions` preserves its selected response contract and unknown-create attribution limits |
| Connections | 3.2 typed create DTO adds defaults including `ai_access_level=allow`; the plugin's raw snapshot create/replace preserves explicit values and absent fields without injecting those defaults, verified for both installations |
| Errors/readback | SDK HTTP module is unchanged; retain bounded response/error handling, no write retries, lost-response receipts, identity checks and independent saved/published reads |

Official comparisons: [3.0 to 3.1](https://github.com/datalens-tech/datalens-sdk/compare/v3.0.0...v3.1.0),
[3.1 to 3.2](https://github.com/datalens-tech/datalens-sdk/compare/v3.1.0...v3.2.0).
New cloud infrastructure APIs and connector types do not expand this plugin's
closed public tool surface. Historical request hashes/receipts are not rewritten.

| Configuration | SDK / authentication | HTTP contract |
|---|---|---|
| `DATALENS_INSTALLATION=yacloud` (default) | `DataLensClientYC`, static IAM token + organization; existing optional YC refresh | Explicit `DATALENS_API_BASE_URL` or the established cloud API default; API version 3, organization header |
| `DATALENS_INSTALLATION=enterprise` | `DataLensClientEnterprise`, `DATALENS_TOKEN` static Bearer token | Explicit deployment `DATALENS_API_BASE_URL`; API version 3, no cloud organization header |

Unknown installations, Enterprise with the cloud default, and Enterprise with YC
refresh enabled fail locally. The SDK receives the configured API endpoint; the
UI hostname is never used to infer one. Enterprise service-account token exchange
is an upstream capability, not a new credential flow in this MCP. Configure the
selected deployment's supported static credential. No cloud fallback occurs.

`dl_server_info.runtime.sdk_version` records the loaded SDK version once. The
separate `installed_sdk_version` and `active_sdk_matches_installed` fields expose
a disk upgrade without pretending the active process has reloaded.

## Used contracts

All listed provider calls use `x-dl-api-version: 3`. Read responses retain the
existing MCP identity/branch/full-state projection.

| Public request | Adapter / SDK contract | Endpoint and preservation |
|---|---|---|
| Dataset create | Existing typed source/field builder | `createDataset`; installed installation-specific DTOs |
| Dataset full or narrow update | Real SDK `get.dataset` plus the existing narrow full-state adapter | `updateDataset`, `datasetId` + `data.dataset`; outer saved revision and inner `dataset.revision_id` checked independently |
| Wizard create/update | Typed GUID-based create builders; SDK raw replacement of document **V1** | `createWizardChart` / `updateWizardChart`; `sources.datasetsIds`, GUID+dataset handles, ordered visualization slots |
| Editor create/update | Renderer builder / raw replacement, with changed-tab validation against generated update carriers | `createEditorChart` / `updateEditorChart`; preserve untouched tabs, `meta` aliases, links, unknown unchanged fields; SDK strips UI-managed secrets |
| Dashboard create/update | Typed `DashboardTab` or guarded V2 snapshot / SDK raw replacement | `createDashboard` / `updateDashboard`; 36-column geometry, explicit tabs, IDs, order, hidden state, selectors and bindings remain intact |
| Preview | `client.data.get_dataset_data`, real filter/parameter/sort DTOs | `getDatasetData`; requested GUIDs, rows and columns bounded; malformed/error responses never become empty success |
| Navigation and relations | Existing bounded read adapter; SDK navigation filter contract independently exercised | `getWorkbooksList`, `getWorkbookEntries`, `getEntriesRelations`; unknown read scopes retained, continuation and partial state preserved |
| Publish saved Dashboard/Wizard/Editor | SDK `publish_revision(rev_id=observed)` after fresh preflight | `updateDashboard` / `updateWizardChart` / `updateEditorChart`, publish mode plus exact revision; readback must match that revision |
| Existing HTML Page metadata/publication | Narrow documented API adapter | `getHtmlPage`; `updateHtmlPage` with `entryId`, `mode=publish`, `revId`; fresh identity/branch/revision preflight and exact published readback |
| QL publication | Existing full-content SDK save in publish mode | Publishes the freshly read saved content; the SDK does not expose a separate existing-revision publication method |

Dataset raw replacement in SDK 3.2.0 still invokes
`converter/raw/dataset.py:dataset_content_from_snapshot`, which strips
`revision_id` with create-time server fields. Removing the narrow adapter would
regress the inner-revision contract. It therefore remains a single existing
mutation path, with API v3 headers and both preconditions; it does not introduce a
second writer or receipt system. Unknown Dataset fields, explicit null, empty
arrays, and empty strings are preserved. Protocol revision locations and the documented read-only Dataset
`sources[].parameter_hash` are excluded from business readback matching: a nested business `revision` field
remains significant. An explicit null `dataset.revision_id` is preserved when the fresh read also returns null and the independently checked outer revision is present. Missing or changed inner revisions still fail before dispatch; the outer revision is never copied into the inner field. Preflight is not an atomic provider-side CAS guarantee.

SDK 3.1 fixes the former Wizard raw-save revision selection. The adapter now
passes the original target to `client.raw.replace.wizard_chart`, with no copy or
protocol-field removal. A real SDK transport regression checks ordinary save
omits `revId`, persists the requested full content and preserves unrelated state.
Exact publication returns through `publish_revision` before raw replacement.

## Compatibility boundaries

- A legacy Wizard V2 snapshot cannot be copied into the V1 wire schema. Re-export
  using API v3, or rebuild through a typed recipe using current exact Dataset
  GUIDs. Duplicate labels are never a field identity. Removed setters fail before
  mutation dispatch; local fields now use `WizardLocalField` handles.
- A Dashboard snapshot declaring document version 1 is rejected with an explicit
  re-export/migration instruction. Raw imported Dashboard artifacts require
  `entry.version=2`. A fresh API v3 read has the V2 contract; versionless current
  reads are accepted under that contract. Existing V2 coordinates are never
  scaled. Raw and typed creation require a tab. This is structural evidence,
  not rendered evidence.
- Editor writable tabs depend on the subtype and installation. Activities is
  supported for table/Gravity/selector and rejected for Markdown/Advanced;
  the adapter checks introduced or changed tabs against the installed carriers. Legacy secrets are stripped by
  SDK reads/replacements; attempts to introduce UI-managed fields are rejected.
- HTML Page method names exist in both upstream specifications, but
  `GetHtmlPageResult` provides metadata and `meta.objectId`, not HTML content.
  The adapter rejects Page creation/content updates before dispatch because it
  cannot prove content readback. Keep a local UTF-8 HTML artifact instead.
  Metadata and revision publication do not certify Page content or rendering.
  No new content-fetch/upload endpoint is invented. Editor HTML remains a
  separate renderer contract.
- Dataset, connection and workbook have no separate supported publish branch.
  Save-only never invokes publication. QL publish proves the saved content
  sent and the published content read back; it does not claim publication of an
  unchanged revision ID. Dashboard, Wizard and Editor require exact revision readback.
- Preview zero rows means the bounded query returned zero rows, not that its
  source is empty. 403, source/server errors, malformed response, and transport
  failure remain errors. Preview is never rendering proof.

## Historical 3.0 migration evidence

These recorded counts and failures describe the original 3.0 migration. The
current 3.2 contract matrix above supersedes its workaround decisions. Existing
regressions remain in their original files and run against the current pin.

### Acceptance evidence

Tests intercept HTTP only for the new public-handler cases; runtime injection
selects synthetic configuration. Real SDK builders, DTOs, services, readback and
operation storage execute. No provider credential or real DataLens object is
used. Provider fixtures are synthetic and contain explicit negative controls.

| Acceptance | Tests in `tests/replacement/` |
|---|---|
| D-S01 | `test_sdk_v3_transport.py`: `test_public_dataset_full_state_and_reconcile` (both installations), `test_public_dataset_wrong_business_revision_is_mismatch`, `test_public_dataset_wrong_description_at_new_revision_is_mismatch`; existing `test_dataset_update_wire.py` |
| D-S02 | `test_public_dataset_stale_then_fresh_patch_preserves_manual_filter`, `test_second_sdk_fetch_rejects_wrong_target_or_branch_before_write`; existing `test_sdk_revision_guard.py` |
| D-S03 | `test_public_wizard_guid_payload_v1_and_unsupported_setter`, `test_public_wizard_update_keeps_guid_bindings_and_order`, `test_public_wizard_duplicate_label_is_not_a_guid`, `test_wizard_legacy_v2_artifact_rejected_locally`; updated `test_l04_dataset_wizard.py`, `test_typed_wizard_write.py` |
| D-S04 | `test_public_editor_one_tab_preserves_others_and_strips_secrets`, `test_public_editor_activities_rejected_before_network_write`, `test_raw_editor_create_cannot_bypass_activities_contract` |
| D-S05 | `test_public_dashboard_v2_geometry_unchanged`, `test_public_dashboard_legacy_layout_requires_explicit_migration`, `test_public_raw_dashboard_create_requires_tab_and_known_schema`; `test_typed_dashboard_graph.py` |
| D-S06 | `test_public_preview_real_sdk_bounded_and_distinct`, `test_preview_refresh_uses_runtime_owner_once`, `test_public_relations_preserve_unknown_scope_and_page_cursor`, `test_sdk_navigation_unknown_request_scope_rejected_before_transport` |
| D-S07 | `test_public_publish_uses_exact_saved_revision`, `test_public_publish_third_revision_is_not_success`, `test_html_page_metadata_and_exact_revision_publish`; existing lifecycle/readback tests |
| D-C01 | Existing `test_mutation_admission_contract.py`: multiprocess admission/digest/network-lock cases |
| D-C02 | Existing `test_write_interruption.py`, `test_sdk_transport_no_replay.py`, lifecycle/reconcile cases; no receipt format reset |
| D-C03 | Existing `test_snapshot_continuation.py`: bounded continuation, scope drift, source revision drift, unknown dependency and partial-result cases |
| D-C04 | Existing `test_tool_contracts.py` and compact operation/snapshot cases; model behavior and host metrics require separate evaluation |

Baseline at `d70787c`: **396 passed** with SDK 0.9.0. The first environment command
found pytest absent from the `dev` extra; pytest was installed in the isolated
worker environment, then the baseline passed. The initial v3 focused run had
5 failures / 34 passes (old pin/wire assertions and removed local-field API).
New red controls exposed mixed API headers, the cloud-only client factory,
unsupported raw Editor Activities, over-limit/empty-on-malformed preview,
Dashboard replacement instead of exact publication, acceptance of a third
published revision, Page content readback gaps, and a second-fetch identity/branch
guard gap. Each was corrected and rechecked. Interim harness mistakes (MCP result
envelope, incomplete strict Wizard response fixture, generated carrier naming,
numeric layout DTO coordinates, navigation method/result names, and old fake
preview-runtime shape) were corrected without treating them as provider evidence.
Old expected-wire fixtures were updated to V1 slots and exact-revision publication.

The final affected contour passed **232 tests**, including the new transport
regressions and existing concurrency, interruption, and continuation cases.
Changed Python files passed Ruff. Final full repository, build/install, active native runtime and host evaluation
are integration checks, recorded separately by the release owner. Live mutation,
rendering and business acceptance were **not run** by this migration worker.

### Follow-up ordinary-save regression

A late additional Wizard update test failed after the first commit because its
ordinary-save DTO still contained `revId`. With synthetic existing-revision
semantics, readback remained unchanged and correctly reported a mismatch. The
save-only domain-handle adaptation above corrected the wire request; the test
now proves changed slot order, preserved dataset/GUID associations and an unknown
nested business `revision`. Dashboard ordinary save passed its no-`revId` control
before the fix. The follow-up focused contour passed **59 tests**, including all
43 new transport cases, revision preflight, typed Wizard authoring, exact
publication, wrong description and unbranched-publication negative controls.
All attempts remain recorded; the first commit alone is insufficient for this
Wizard save case. Integration must include this follow-up before its final suite.

### Final integration review corrections

The integration full suite exposed four recipe failures (446 passed). A focused
reproduction confirmed three stale V2 wire assertions and one product defect:
the pivot recipe still emitted the removed `y` measure role. It now emits the
SDK V1 `measures` role. The four recipe tests assert exact dataset/GUID bindings,
slot order, dimension subtotals and display settings from the real SDK converter.
This extends D-S03 coverage; no chart formula or field identity is inferred.

Independent review also supplied two reproducible input/readback gaps. Four
public Editor update cases accepted non-string changed tabs before the fix.
Changed values now validate against the generated renderer carrier's field
type before dispatch; unchanged unknown state remains intact (D-S04). Preview
now requires each page's returned schema GUIDs and order to match the requested
columns before accepting its rows (D-S06). Three negative transport cases cover
wrong GUIDs, reordered columns and second-page drift; a positive two-page case
checks values and offsets. The initial preview test setup lacked the required
deterministic pagination sort; after correcting that fixture, all three cases
reproduced false success before the implementation change.

The final focused/affected contour passed **102 tests**, including **51 real-SDK
transport cases**, the four recipe suites, L04/L05, typed Wizard and Editor
alias/tab dispatch tests. The preview component fixture now includes its schema.
No additional full suite, build or live provider operation was run by this worker.
