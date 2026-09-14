---
name: datalens-maintenance
description: Use when exporting DataLens backups, inspecting administrative capabilities, previewing or applying dependency-safe cleanup, or working on standalone HTML Pages. Not for Editor HTML cells, ordinary chart authoring, or RLS identity lookup.
---

# DataLens Maintenance

Read [maintenance boundaries](references/boundaries.md) for backup completeness, dependency previews and supported administration. For standalone HTML reports load [HTML Pages](references/html-pages.md); a reference describes a contract, not proof that this installation exposes it.

Work from the exact project/subproject. For backup or cleanup, inventory the requested scope completely and retain partial/unresolved results. An administration inventory or Page metadata question needs only addressed reads; do not start a cleanup or visual cycle.

Follow [authorized scope and delivery](../datalens-dashboard/references/authorized-scope.md) for effects and multi-object completion. Route ordinary reads and cloud RLS subject resolution to `datalens-inspect`, dashboard composition to `datalens-dashboard`, native fields/charts to `datalens-dataset-wizard`, and HTML inside JavaScript charts to `datalens-editor`.
