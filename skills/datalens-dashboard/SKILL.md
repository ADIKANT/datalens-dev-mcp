---
name: datalens-dashboard
description: Use when composing, updating, or visually verifying DataLens dashboard tabs, widgets, selectors, parameters, relations, styles, or layout. Not for standalone HTML Pages, SDK scripts, or metadata-only inspection.
---

# DataLens Dashboard

Apply explicit requirements, then the explicit reference, project defaults, user defaults and the generic recipe. Keep object name, visible title, hint and geometry separate. Preserve current tabs, widgets, relations and manual layout outside the requested change.

Read [composition](references/composition.md) for selector bindings, typed dashboard drafts and dependency order. Validate the complete draft batch with `dl_editor_validate(drafts=...)`; carry a compiled recipe's `visual_contract` into item `presentation`. Retain raw snapshots for exact imports or documented adapter gaps.

Follow [authorized scope and delivery](references/authorized-scope.md) for mutations, continuation and completion across projects. For a visual or semantic choice, load the relevant part of [visualization decisions](references/decision-quality.md). Check the changed rendered state with Browser after API and applicable data checks; a correct readback alone does not prove correct layout.

Route field/native chart changes to `datalens-dataset-wizard`, JavaScript runtime changes to `datalens-editor`, discovery to `datalens-inspect`, and backup/cleanup or standalone Page work to `datalens-maintenance`.
