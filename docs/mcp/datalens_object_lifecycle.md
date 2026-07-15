# DataLens Object Lifecycle

The lifecycle surface separates object operations from route selection.

## Supported Read Operations

- workbooks: `dl_list_workbooks`
- workbook entries: `dl_get_workbook_entries`
- dashboard: `dl_get_dashboard` or `dl_read_object(object_type="dashboard")`
- Editor/Advanced chart: `dl_get_editor_chart` or `dl_read_object(object_type="editor_chart")`
- Wizard chart: `dl_get_wizard_chart` or `dl_read_object(object_type="wizard_chart")`
- dataset: `dl_get_dataset` or `dl_read_object(object_type="dataset")`
- connection: `dl_get_connection` or `dl_read_object(object_type="connection")`
- connector: `dl_get_connection` or `dl_read_object(object_type="connector")`
- relations: `dl_get_entries_relations` or `dl_list_related_objects`

## Guarded Write Planning

Editor chart, Wizard chart, dashboard, dataset, and connector create/update
methods exist in the curated API catalog. The MCP tools produce guarded plans
only:

- normal work should use `dl_plan_object_create`,
  `dl_plan_object_update`, `dl_validate_object`, and
  `dl_create_publish_from_saved_plan`
- create plans use `{entry}` and omit `mode`
- update/save/publish plans use `{mode, entry}`
- dataset and connector create/update plans use the direct official payload
  shape instead of the dashboard/chart `{entry}` wrapper
- `connection` is read-only in generic lifecycle tools; request
  `object_type="connector"` or use `dl_create_connector_plan` /
  `dl_update_connector_plan` for guarded `createConnection` /
  `updateConnection` planning
- `mode` appears in compiled payloads only when the OpenAPI request schema
  supports it
- publish from saved readback is explicit through `dl_create_publish_from_saved_plan`;
  `dl_plan_publish_from_saved` remains compatibility-only
- all write execution still goes through safe apply
- update plans require fresh readback discipline and preserve revision/unknown
  fields for existing objects

The shared compiler accepts named adapters only: `canonical_object_payload`,
`canonical_request_payload`, `rpc_readback_envelope`, `saved_entry`,
`published_entry`, `artifact_path`, and `project_manifest_reference`. Raw RPC
readbacks and summary-only compact reads are not silently treated as mutation
requests.

### Guarded Dataset Update

Use `dl_plan_guarded_dataset_update` for dataset fixes that would otherwise
require a local script. The plan is still non-executing, but it records the
required sequence:

1. fresh `getDataset`
2. `validateDataset`
3. approved `updateDataset` only when `validate_only=false` and `approved=true`
4. saved `getDataset` readback

Field GUIDs are preserved by default. The tool blocks if a proposed payload
changes or drops field GUIDs without `approve_guid_changes=true`, and it also
checks affected chart payloads so chart wiring does not keep references to
missing dataset field GUIDs. Publishing remains an internal publish-from-saved
operation governed by `delivery_intent_decision`.

### Scoped Dashboard Tab Update

Use `dl_plan_dashboard_tab_update` when adding or replacing one dashboard tab.
The tool works from a fresh dashboard payload, appends or replaces only the
requested tab, keeps unrelated tabs byte-for-byte equivalent, and preserves
existing dashboard metadata. It does not force title/hint rewrites on unchanged
legacy widgets. Save readback and publish remain separate internal steps, and
approved implementation/fix/enhance delivery continues to publish only through
fresh saved readback.

## Schema-Only Objects

Dataset field and calculated field create/update operations are represented by
schemas and dataset-update guidance because no standalone official RPC method is
available. Tools return `unavailable_api_method` with the relevant schema path
instead of pretending the standalone method exists.

## Safety

Lifecycle tools reject payload keys containing token, authorization, password,
secret, IAM, or subject token wording. Wizard create accepts only canonical
visualization IDs and validated canonical templates or fresh same-ID saved
seeds; unknown IDs are update-only from fresh saved readback. QL create/update
requires `ql_explicit` plus direct-request provenance and an explicit payload or
fresh saved seed. QL delete remains closed.
