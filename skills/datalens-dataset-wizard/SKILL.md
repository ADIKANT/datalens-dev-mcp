---
name: datalens-dataset-wizard
description: Use when creating, updating, validating, or previewing DataLens datasets and native Wizard charts.
---

# DataLens Dataset and Wizard

Read [references/dataset-wizard-contracts.md](references/dataset-wizard-contracts.md) before validating fields, previewing data, or authoring Wizard charts.

Use exact Dataset field GUIDs from current readback. Treat row expressions, aggregates, windows and LOD as different calculation levels. Prefer Wizard for a new standard visualization unless the user requires another technology; preserve an existing object's technology. Compile field roles with the pinned official SDK and do not call `.build()` for preview.

Preserve field GUIDs and distinguish dataset-global fields from chart-local fields. For a new Dataset, use the short typed `dataset` draft with top-level `object_type`, `name`, and `client_ref`, plus an existing `connection_id`, source, and fields inside the nested `dataset` object. Do not move those three members to the draft root and do not synthesize a raw provider snapshot. Bind real fields to supported Wizard roles and sections. Treat Measure Names and Measure Values as chart technical fields, never physical dataset columns. Validate provider acceptance separately from the rendered result.

Follow [authorized scope and delivery](../datalens-dashboard/references/authorized-scope.md) for mutations: explicit scoped work continues without repeated permission questions; read-only and save-only limits remain binding.

For new visual or semantic decisions, consult only the relevant part of [visualization decisions](../datalens-dashboard/references/decision-quality.md); preserve the accepted reference and infer routine context without a mandatory questionnaire.
