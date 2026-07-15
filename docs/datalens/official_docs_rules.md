# Official DataLens Documentation Rules

Sources:

- <https://yandex.cloud/ru/docs/datalens/>
- <https://yandex.cloud/ru/docs/datalens/charts/editor/>
- <https://api.datalens.tech/>

The compact knowledge registries preserve per-record source URLs and hashes.
See `docs/source_provenance.md` and `THIRD_PARTY_NOTICES.md`.

## Object Model

- A workbook is the normal container for connections, datasets, charts,
  dashboards, and reports. Creation plans therefore carry workbook context.
- Use the entry relation graph as evidence for object dependencies instead of
  guessing them.
- Dashboard widgets, selectors, parameters, tabs, links, and layout belong to
  dashboard and relation payloads, not hidden chart-body code.

## API And Authentication

- Use the documented RPC method names and the compiled current API version.
- Live calls require bearer IAM authentication and an organization identifier.
  Committed examples contain placeholders only.
- Token refresh is an operator concern. Logs and reports must never reveal
  tokens, authentication headers, or subject-token material.
- Authentication and permission failures stop the workflow unless an explicit
  configured refresh flow is available.

## Save, Publish, And Readback

- Startup is read-only; write and publish gates are disabled by default.
- An update begins from a fresh saved object, preserves its revision and unknown
  fields, changes only declared fields, and finishes with saved readback.
- Publishing is a separate action built from saved readback and followed by
  published readback.
- Draft, review, plan-only, save-only, or no-publish instructions always block
  publishing.

## Chart Routing

- New standard charts use `wizard_native`; maps use visualization ID
  `geolayer` and require geographic evidence.
- Advanced Editor is selected only by explicit request or a registered
  capability gap. It is never a transport fallback.
- QL is available only through `ql_explicit` after a direct QL request. The
  server never selects or generates QL automatically.
- Updates preserve the saved chart technology and visualization identifier
  unless the user explicitly requests a migration.

## Datasets And Connections

- Dataset and connection reads and validation may be executed when credentials
  are configured. Writes remain guarded and plan-only by default.
- Connection payloads are credential-sensitive and must pass redaction and
  sensitive-key validation.
- Dataset fields, calculations, measures, joins, filters, and row-level security
  are modeled within dataset payloads.

## Administrative Operations

- Access-binding reads may be used as evidence; updates are admin-sensitive and
  guarded.
- Delete, move, rename, and license-management operations are documented for
  awareness but are outside normal operator routing.
