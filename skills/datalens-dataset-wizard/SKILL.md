---
name: datalens-dataset-wizard
description: Create, update, validate, and preview DataLens datasets and native Wizard charts with real field and aggregation contracts.
---

# DataLens Dataset and Wizard

Read [references/dataset-wizard-contracts.md](references/dataset-wizard-contracts.md) before validating fields, previewing data, or authoring Wizard charts.

Use exact Dataset field GUIDs from current readback. Treat row expressions, aggregates, windows and LOD as different calculation levels. Prefer Wizard for a new standard visualization unless the user requires another technology; preserve an existing object's technology. Compile field roles with the pinned official SDK and do not call `.build()` for preview.

Preserve field GUIDs and distinguish dataset-global fields from chart-local fields. Bind real fields to supported Wizard roles and sections. Treat Measure Names and Measure Values as chart technical fields, never physical dataset columns. Validate provider acceptance separately from the rendered result.
