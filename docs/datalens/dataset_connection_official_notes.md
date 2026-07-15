# Dataset And Connection Official Notes

Sources: the public DataLens API, the official DataLens documentation, and the
compiled request/response schemas tracked by this project.

## Supported API Surface

- `getConnection`, `getDataset`, and `validateDataset` are read-only or validation evidence and can be called only with credentials.
- `createConnection`, `updateConnection`, `createDataset`, and `updateDataset` are official methods, but MCP exposes them as safe-apply plans by default.
- Dataset/connection object planning is separate from chart generation; charts must not smuggle connection or dataset mutations in template code.

## Connection Rules

- Connection payloads may include host, port, database path, username, SSL, SQL access level, and connector-specific credential fields. Any generated example must use placeholders and must pass sensitive-key validation.
- SQL access level can enable subqueries, source parameterization, and QL chart capability in DataLens, but this repo still keeps QL outside chart creation routing.
- Connection info/hints are metadata for users; they should not be copied into chart body code.

## Dataset Rules

- Dataset payloads own source tables, joins, fields, calculated fields, dimensions, measures, aggregations, default filters, and row-level security.
- There is no standalone official field or calculated-field RPC in the reconciled method catalog. MCP field tools therefore return schema/payload plans, not executable API calls.
- Use `validateDataset` where credentials exist before chart payload planning; offline plans must mark dataset validation as pending.
- Field references in chart templates must be validated against a dataset schema or persisted requirements before generation.
- Use `dl_plan_guarded_dataset_update` for dataset updates. It requires a
  fresh current dataset payload, validates the proposed payload first, preserves
  field GUIDs by default, and checks affected chart payloads for broken GUID
  references before it builds an executable update plan.

## Safe Apply Rules

- Create/update plans must preserve unknown fields from fresh readback when updating existing objects.
- Dataset and connection update plans must name the official method, schema ref, and support status from `config/datalens_api_methods.json`.
- Saving a dataset, chart, or dashboard is followed by saved readback.
  Implementation/fix/enhance delivery publishes through a publish-from-saved
  plan and then verifies published readback.
- Do not log or commit credential-like connection payloads, env files, or token material.
