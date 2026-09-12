---
name: datalens-inspect
description: Use when reading DataLens metadata, authentication, workbook inventory, relations, current errors, or cloud RLS subject identities without changing objects or access. Not for authoring, backup, or independent SDK scripts.
---

# DataLens Inspect

Start from the exact project and target URL or ID. Reuse its configured installation, API endpoint and organization; consult [installation and interfaces](references/installation-and-sdk.md) when those are unclear or the request concerns SDK scripting. Read only dependencies needed for the question. A metadata audit needs neither new project files nor an SDK bootstrap; a legacy manifest is not required.

Use [direct reads](references/direct-reads.md) for tool selection, compact projections, pagination and completeness. Distinguish saved and published branches, target and reference, source/static validation and live data or Browser evidence. A rendered-result request can use read-only Browser inspection after scoped API and applicable data checks.

For cloud identity lookup load [RLS resolution](references/cloud-rls-resolution.md). For changes route to `datalens-dataset-wizard`, `datalens-editor` or `datalens-dashboard`; backup, standalone HTML Page and cleanup belong to `datalens-maintenance`. Load only the addressed reference.

[Upstream provenance](references/upstream-provenance.md) records the selectively adapted sources; load it only for a version/provenance question.
