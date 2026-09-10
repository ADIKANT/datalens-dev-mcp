---
name: datalens-dashboard
description: Use when composing or updating DataLens dashboards, widgets, tabs, selectors, parameters, relations, styles, or layout.
---

# DataLens Dashboard

Separate object name, visible title, hint, and geometry. Apply explicit requirements first, then an explicit reference, project defaults, user defaults, and the generic recipe. For new recipe charts, carry the compiled `visual_contract` into item `presentation` so the selected title and hint owner survives placement; see the canonical example in the composition reference. On update, preserve live tabs, widgets, relations, and manual layout outside the requested change.

Use this skill when the requested result is a dashboard composition or layout change. Route Dataset fields and native Wizard authoring to `datalens-dataset-wizard`, Editor runtime work to `datalens-editor`, read-only discovery to `datalens-inspect`, and backup or cleanup to `datalens-maintenance`. Load only the reference named for the current decision.

Read [references/composition.md](references/composition.md) before composing selectors, parameters, or multi-object dashboards. Validate the full batch with `dl_editor_validate(drafts=...)`, then create dependencies in explicit order. Use the typed `dashboard` draft for ordinary tabs/widgets and retain raw snapshots for exact imports or documented SDK gaps.

Follow [authorized scope and delivery](references/authorized-scope.md) for mutations: explicit scoped work continues without repeated permission questions; read-only and save-only limits remain binding.

For new visual or semantic decisions, consult only the relevant part of [visualization decisions](references/decision-quality.md); preserve the accepted reference and infer routine context without a mandatory questionnaire.
