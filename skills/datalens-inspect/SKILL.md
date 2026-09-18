---
name: datalens-inspect
description: Use when reading DataLens metadata, authentication, workbook inventory, relations, current errors, or cloud RLS subject identities without changing objects or access. Not for authoring, backup, or independent SDK scripts.
---

# DataLens Inspect

Start from the exact project and target URL or ID. Reuse its configured installation, API endpoint and organization; consult [installation and interfaces](references/installation-and-sdk.md) when those are unclear or the request concerns SDK scripting. Read only dependencies needed for the question. Reuse already established runtime identity; SDK documentation is needed only for an unknown contract or changed version, not after each call. A metadata audit needs neither new project files nor an SDK bootstrap; a legacy manifest is not required.

For a known target confirmed by the current project and API, read that object and only the bindings needed for the question. A workbook URL alongside an exact dashboard/chart ID does not require another workbook card or inventory. Use the workbook's card and paginated inventory when selecting an unknown target, discovering a requested set or proving completeness/absence. Retain the returned completeness boundary; absence from a partial listing proves nothing. Classify actual type/subtype and renderer metadata, distinguishing Wizard, Editor, QL and HTML Page; resolve unknown subtypes with addressed reads. Project examples and browser tabs cannot replace the requested container.

Use [direct reads](references/direct-reads.md) for tool selection, compact projections, pagination and completeness. Distinguish saved and published branches, target and reference, source/static validation and live data or Browser evidence. A rendered-result request can use read-only Browser inspection after scoped API and applicable data checks.

For token renewal or a credential failure, follow [authentication recovery](references/installation-and-sdk.md#authentication-recovery): `dl_auth_refresh` supports the existing profile's external-browser sign-in. A noninteractive timeout alone is not a login prohibition.

For cloud identity lookup load [RLS resolution](references/cloud-rls-resolution.md). For changes route to `datalens-dataset-wizard`, `datalens-editor` or `datalens-dashboard`; backup, standalone HTML Page and cleanup belong to `datalens-maintenance`. Load only the addressed reference.

[Upstream provenance](references/upstream-provenance.md) records the selectively adapted sources; load it only for a version/provenance question.
