# SDK 3.0.0 compatibility

This change retains the typed public operations, mutation receipts, request digests,
process claims, fresh saved-state merge, adapter preflight, and independent readback.
The SDK migration is separate from package versioning. No runtime SDK auto-upgrade
or generic write gateway is introduced.

## Pinned upstream and installation

The dependency is `datalens-sdk==3.0.0`, from the official
[datalens-tech/datalens-sdk](https://github.com/datalens-tech/datalens-sdk) project.
The annotated `v3.0.0` tag resolves to commit
`9114d148ed9ffa2524933988831384184d9db01b`; the tag object is
`f2ee038d647cff969816246e3b0c7a53b5d42480`, not the source commit.
The [changelog](https://github.com/datalens-tech/datalens-sdk/blob/9114d148ed9ffa2524933988831384184d9db01b/CHANGELOG.md),
installed `agent_skill_paths()` documentation, installed generated DTOs, and both
`spec/yacloud.json` and `spec/enterprise.json` were inspected. Upstream is
[Apache-2.0](https://github.com/datalens-tech/datalens-sdk/blob/9114d148ed9ffa2524933988831384184d9db01b/LICENSE).
The adapter imports its installed carriers; it does not vendor the upstream tree,
skill, or OpenAPI files. The Editor carrier mapping is derived from
`converter/editor_chart.py` at that commit.

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
| Publish saved Dashboard/Wizard | SDK `publish_revision(rev_id=observed)` after fresh preflight | `updateDashboard` / `updateWizardChart`, publish mode plus exact revision; readback must match that revision |
| Existing HTML Page metadata/publication | Narrow documented API adapter | `getHtmlPage`; `updateHtmlPage` with `entryId`, `mode=publish`, `revId`; fresh identity/branch/revision preflight and exact published readback |
| Editor/QL publication | Existing full-content SDK save in publish mode | Publishes the freshly read saved content; those SDK DTOs do not expose a separate existing-revision publication method |

Dataset raw replacement in SDK 3.0.0 still invokes
`converter/raw/dataset.py:dataset_content_from_snapshot`, which strips
`revision_id` with create-time server fields. Removing the narrow adapter would
regress the inner-revision contract. It therefore remains a single existing
mutation path, with API v3 headers and both preconditions; it does not introduce a
second writer or receipt system. Unknown Dataset fields, explicit null, empty
arrays, and empty strings are preserved. Only protocol revision locations are
excluded from business readback matching: a nested business `revision` field
remains significant. Preflight is not an atomic provider-side CAS guarantee.

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
- Activities is absent from the generated Editor writable carrier. The upstream
  shared update facade/raw path can still accept it, so this adapter checks
  introduced or changed tabs before dispatch. Legacy secrets are stripped by
  SDK reads/replacements; attempts to introduce UI-managed fields are rejected.
- HTML Page method names exist in both upstream specifications, but
  `GetHtmlPageResult` provides metadata and `meta.objectId`, not HTML content.
  The adapter rejects Page creation/content updates before dispatch because it
  cannot prove content readback. Keep a local UTF-8 HTML artifact instead.
  Metadata and revision publication do not certify Page content or rendering.
  No new content-fetch/upload endpoint is invented. Editor HTML remains a
  separate renderer contract.
- Dataset, connection and workbook have no separate supported publish branch.
  Save-only never invokes publication. Editor/QL publish proves the saved content
  sent and the published content read back; it does not claim publication of an
  unchanged revision ID.
- Preview zero rows means the bounded query returned zero rows, not that its
  source is empty. 403, source/server errors, malformed response, and transport
  failure remain errors. Preview is never rendering proof.

## Acceptance evidence

Tests intercept HTTP only for the new public-handler cases; runtime injection
selects synthetic configuration. Real SDK builders, DTOs, services, readback and
operation storage execute. No provider credential or real DataLens object is
used. Provider fixtures are synthetic and contain explicit negative controls.

| Acceptance | Tests in `tests/replacement/` |
|---|---|
| D-S01 | `test_sdk_v3_transport.py`: `test_public_dataset_full_state_and_reconcile` (both installations), `test_public_dataset_wrong_business_revision_is_mismatch`; existing `test_dataset_update_wire.py` |
| D-S02 | `test_public_dataset_stale_then_fresh_patch_preserves_manual_filter`, `test_second_sdk_fetch_rejects_wrong_target_or_branch_before_write`; existing `test_sdk_revision_guard.py` |
| D-S03 | `test_public_wizard_guid_payload_v1_and_unsupported_setter`, `test_wizard_legacy_v2_artifact_rejected_locally`; updated `test_l04_dataset_wizard.py`, `test_typed_wizard_write.py` |
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
