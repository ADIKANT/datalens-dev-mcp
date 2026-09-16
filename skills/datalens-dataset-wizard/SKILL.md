---
name: datalens-dataset-wizard
description: Use when creating, updating, validating, or previewing DataLens datasets and native Wizard charts. Not for metadata-only reads, cloud identity lookup, standalone HTML, or independent SDK scripting.
---

# DataLens Dataset and Wizard

Work from the exact dashboard project/subproject. A description-only edit needs a narrow patch and saved readback. Field, formula, filter or source changes also need applicable field validation and bounded data preview; JSON alone cannot prove metric meaning. Use [Dataset/Wizard contracts](references/dataset-wizard-contracts.md) for typed drafts, field roles, preview and revision-safe updates. Use current field GUIDs; ambiguous labels cannot identify fields. Preserve dataset-global versus chart-local fields, calculation levels, field order and the existing object's technology. Prefer Wizard for new standard charts unless the user requests another route or a documented gap requires it.

For a new metric or upstream-dependent field, first follow [current source readiness](references/dataset-wizard-contracts.md#current-source-readiness). A merged change or green CI does not prove that this connection exposes the field or data. Complete independent authorized edits while naming the dependent remainder.

A new `dataset` draft keeps `object_type`, `name` and `client_ref` at its root; `connection_id`, source and fields belong inside `dataset`. Use typed public operations; the backend compiles against its pinned SDK. Measure Names and Measure Values are chart technical fields, not physical columns.

Follow [authorized scope and delivery](../datalens-dashboard/references/authorized-scope.md). Load [visualization decisions](../datalens-dashboard/references/decision-quality.md) only for the relevant semantic choice. Preview establishes bounded data evidence; provider acceptance and rendered results require their own checks.

Route placement to `datalens-dashboard`, JavaScript variants to `datalens-editor`, metadata or RLS identity lookup to `datalens-inspect`, and backup/cleanup to `datalens-maintenance`.

For unknown effects follow [repeat-effect recovery](../datalens-dashboard/references/authorized-scope.md#unknown-outcomes-and-repeat-effects): only proven non-application or separate informed repeat authorization permits another attempt. Failed reconciliation, absent inventory and a new operation_id do not make a retry safe.
