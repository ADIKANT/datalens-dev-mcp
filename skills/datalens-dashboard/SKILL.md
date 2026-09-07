---
name: datalens-dashboard
description: Use when composing or updating DataLens dashboards, widgets, tabs, selectors, parameters, relations, styles, or layout.
---

# DataLens Dashboard

Separate object name, visible title, hint, and geometry. Apply explicit requirements first, then an explicit reference, project defaults, user defaults, and the generic recipe. On update, preserve live tabs, widgets, relations, and manual layout outside the requested change.

Read [references/composition.md](references/composition.md) before composing selectors, parameters, or multi-object dashboards. Validate the full batch with `dl_editor_validate(drafts=...)`, then create dependencies in explicit order. Use the typed `dashboard` draft for ordinary tabs/widgets and retain raw snapshots for exact imports or documented SDK gaps.
