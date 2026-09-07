# datalens-dev-mcp 1.0 documentation

[Русский](README.md) · **English** · [Project home](../README_en.md)

`datalens-dev-mcp` is a local Codex plugin and Python stdio backend for direct typed Yandex DataLens operations. The model selects one of five domain skills; the server contains no task compiler, journal, or workflow engine.

## Current contract

- [Installation](installation.md) — wheel, plugin manifest, and checkout-independent verification.
- [25 MCP tools](tools_en.md) — the closed read, authoring, write, and maintenance surface.
- [Visual property consumers](authoring-property-consumers.md) — where recipe properties are applied and what still needs runtime evidence.
- [Supported SDK/API operations](../src/datalens_dev_mcp/schemas/supported-operations.json) — backend, version, and static boundary for each method.
- [62-outcome coverage map](../src/datalens_dev_mcp/schemas/capability-coverage.json) — a direct owner and honest boundary, not an executable router.

## Domain skills

- [Inspect](../skills/datalens-inspect/SKILL.md)
- [Dataset and Wizard](../skills/datalens-dataset-wizard/SKILL.md)
- [Editor](../skills/datalens-editor/SKILL.md)
- [Dashboard](../skills/datalens-dashboard/SKILL.md)
- [Maintenance](../skills/datalens-maintenance/SKILL.md)

The installed backend's `tools/list` is the canonical runtime contract. Older documents not linked from this index describe pre-1.0 versions and do not define the current surface or lifecycle.
