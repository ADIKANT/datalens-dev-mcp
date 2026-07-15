# Local-Only Safety Model

`datalens-dev-mcp` is a local-only MCP stdio server. It may operate on local project paths, real DataLens object IDs supplied by the operator, read-only diagnostic evidence, and local dashboard artifacts.

Hard exclusions:

- IAM tokens and OAuth/IAM credential values
- env files such as `.env`, `.env.local`, `.datalens.env`, `datalens_token.env`
- `Authorization` headers with live bearer values
- passwords, private keys, key stores, and certificate private material
- hidden destructive DataLens operations in normal workflows

Raw source materials stay outside the tracked repo or under ignored local material paths. Only distilled rules, manifests, configs, schemas, templates, examples, and tests should be committed.

The secret scanner is secret-only by design. It allows local paths and placeholder IDs, but fails on real-looking token/private-key/header leakage.

Deletion is allowed only as an explicit retire lifecycle when the user asks to
remove named unnecessary objects. `retire_legacy_objects` requires exact object
ids/types, workbook id, reason, user request quote or decision id, relation
graph proof, saved and published no-reference proof, dry-run retire plan,
approval provenance, execution summary, and post-retire readback.
