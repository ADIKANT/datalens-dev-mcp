# datalens-dev-mcp

[Русский](README.md) · **English**

A public local MCP plugin for developing and maintaining Yandex DataLens objects. Version 1.0 replaces the internal task workflow with direct typed operations for reads, authoring, save/readback, publish-from-saved, backup, and dependency-safe cleanup.

The plugin is independent from Yandex and operates only with the current user's permissions. It contains no language model, Memory Bank, task compiler/journal, arbitrary RPC/eval, or browser write fallback.

## Quick start

Python 3.11+ is required.

```bash
python3 -m venv .venv
.venv/bin/python -m pip install .
.venv/bin/datalens-dev-mcp --version
```

The stdio connection is declared in [.mcp.json](.mcp.json). For live access, provide your own `DATALENS_ORG_ID` and `DATALENS_IAM_TOKEN`; credential values are never returned by tools.

## Domain path

- Inspect exact IDs, saved/published revisions, complete-or-partial pagination, and direct relations.
- Preserve real Dataset field GUIDs and Wizard aggregation/formula constraints; use bounded `getDatasetData` preview.
- Keep Table, Gravity, Advanced, Markdown, and Selector Editor contracts distinct. Local checks are not presented as browser runtime proof.
- Reuse eight versioned visual recipes: KPI, time comparison, bar, dynamic matrix, weekly totals, cross-tab, native table, and selector. Large JavaScript comes from canonical packaged renderers and stays in a local artifact; MCP returns a compact `draft_reference` by default. The [property-consumer map](https://github.com/ADIKANT/datalens-dev-mcp/blob/main/docs/authoring-property-consumers.md) separates configuration presence from runtime proof.
- Create/update finish with saved readback. Publish is a separate operation sourced only from a fresh saved revision and followed by published readback.
- Backup exports are snapshots, not an unproven full restore. Cleanup requires an unchanged exact delete set.

Default precedence is generic → user → project → explicit reference → explicit call. User config lives at `${XDG_CONFIG_HOME:-~/.config}/datalens-dev-mcp/authoring.json`; project config lives at `.datalens/authoring.json`.

## SDK and API

The official `datalens-sdk==0.9.0` handles supported typed operations. A narrow Public API adapter remains for `getDatasetData`, relations, HTML Page, and license endpoints. MCP and `datalens_dev_mcp.sdk` call the same services.

`.build()` and `.execute()` perform external writes. Pure authoring (`dl_compile_recipe`) makes no network call. SDK raw replace is used only after a fresh read and narrow semantic merge; no general server-side CAS or batch transaction is claimed.

## Boundaries

- Dataset and Connection do not have an invented publish lifecycle.
- Wizard, Editor, and QL are not silently substituted; updates preserve technology.
- `getDatasetData` proves Dataset-backed data, not Editor runtime or a published branch.
- Browser is read-only and used when the task requires rendered evidence, after API/readback and applicable data checks.
- An ambiguous lost response is reconciled by exact ID/revision and never blindly replayed.
- License revoke and generic ACL mutation are not claimed.

The closed tool schemas are returned by tools/list. `datalens_dev_mcp/schemas/capability-coverage.json` maps all 62 public use cases. Five bundled skills load only the references required for the current task.

## Development

```bash
.venv/bin/python -m pip install -e '.[test]'
.venv/bin/pytest -q tests/replacement
python -m build
```

Code is Apache-2.0 licensed. See [NOTICE](NOTICE), [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md), and [LICENSES](LICENSES) for attribution.
