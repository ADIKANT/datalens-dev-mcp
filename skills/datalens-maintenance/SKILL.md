---
name: datalens-maintenance
description: Use when exporting DataLens backups, inspecting administrative capabilities, previewing or applying dependency-safe cleanup, or working on standalone HTML Pages. Not for Editor HTML cells, ordinary chart authoring, or RLS identity lookup.
---

# DataLens Maintenance

Read [maintenance boundaries](references/boundaries.md) for backup completeness, dependency previews and supported administration. For standalone HTML reports load [HTML Pages](references/html-pages.md); a reference describes a contract, not proof that this installation exposes it.

Work from the exact project/subproject. For a complete backup or cleanup, inventory the requested scope completely and retain partial/unresolved results; a partial listing cannot prove absence. Reuse current evidence, but cleanup still needs its fresh dependency preview and preserve checks. An administration inventory or exact Page metadata question needs only the corresponding addressed reads; it does not start a cleanup or visual cycle. Do not repeat completed cleanup merely to validate another change.

Follow [authorized scope and delivery](../datalens-dashboard/references/authorized-scope.md) for effects and multi-object completion. Route ordinary reads and cloud RLS subject resolution to `datalens-inspect`, dashboard composition to `datalens-dashboard`, native fields/charts to `datalens-dataset-wizard`, and HTML inside JavaScript charts to `datalens-editor`.

For unknown effects follow [repeat-effect recovery](../datalens-dashboard/references/authorized-scope.md#unknown-outcomes-and-repeat-effects): only proven non-application or separate informed repeat authorization permits another attempt. Failed reconciliation, absent inventory and a new operation_id do not make a retry safe.
