# Sanitization Policy

This policy keeps authored MCP artifacts safe for local Codex use while
preserving DataLens functionality.

## Placeholder Convention

Use deterministic placeholders for docs, examples, reports, and fixtures:

- `<DL_WORKBOOK_ID>`
- `<DL_DASHBOARD_ID>`
- `<DL_CHART_ID>`
- `<DL_DATASET_ID>`
- `<DL_CONNECTION_ID>`
- `<DL_TOKEN>`
- `<DL_CLOUD_ID>`
- `<ORG_INTERNAL_URL>`
- `<INTERNAL_TABLE_NAME>`
- `<INTERNAL_METRIC_NAME>`
- `<USER_EMAIL>`

Use clearly fake values when tests need concrete IDs:

- `wb_demo_000000000000`
- `chart_demo_0000000000`
- `dataset_demo_00000000`
- `connection_demo_0000`

## Classification Rules

| Classification | Action |
| --- | --- |
| must replace | Replace credentials, auth headers, live tokens, cookies, private keys, sensitive emails, sensitive hostnames, and sensitive raw material references with placeholders. |
| safe generic example | Keep clearly fake placeholders and demo IDs. |
| functional API/schema, keep | Keep DataLens method names, auth flow code, connector/dataset/chart/workbook concepts, schemas, validators, route names, and error handling. |
| unknown, needs manual review | Preserve functionality, list the finding in a report, and ask for review before deleting or replacing it. |

## Non-Removal Rule

Do not remove DataLens API method names, auth flow implementation, object
schemas, connector/dataset/chart/workbook concepts, MCP tool schemas,
validation logic, chart templates, or error handling just because they mention
auth, APIs, workbook IDs, datasets, or object IDs.

## Materials Boundary

Raw S2T, sensitive dashboard requirements, PDFs, screenshots, course materials,
Telegram exports, and raw gallery exports belong in ignored `materials/`.
The MCP server must not depend on ignored materials at runtime.

## Local Evidence Boundary

Tracked files may contain local placeholder IDs, redacted fixtures, and concise
diagnostic summaries. Raw materials and full extraction artifacts stay outside
the tracked repo or under ignored local material paths. Future external sharing
requires a separate review that replaces sensitive paths and identifiers with the
placeholders above.
