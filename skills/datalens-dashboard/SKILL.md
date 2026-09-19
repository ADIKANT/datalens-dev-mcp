---
name: datalens-dashboard
description: Use when composing, updating, or visually verifying DataLens dashboard tabs, widgets, selectors, parameters, relations, styles, or layout. Not for standalone HTML Pages, SDK scripts, or metadata-only inspection.
---

# DataLens Dashboard

For new elements, use the effective authoring profile: current explicit requirements override project and user choices; references supply structure/technology below the common visual policy. `visible_title` is canonical (`title` remains an input alias). Keep object name, visible title, hint and geometry separate. Preserve current tabs, widgets, relations and manual layout outside the requested change.

If the dashboard is known, confirm its current identity, parent and affected bindings through addressed reads; a supplied workbook URL does not add a full inventory step. Establish the workbook card and complete inventory when the target or requested group must be discovered, or completeness/absence must be proved. Reuse sufficient current evidence. Route dependencies by actual subtype/renderer; keep unknown types explicit. Project examples and browser tabs supply context, never a replacement target.

For a single metadata field, read the exact object and send a narrow patch; no graph traversal or Browser tour is needed. For existing tab items, layout or connections, use `dl_object_update` with `dashboard_patch` and the fresh `expected_revision`; send only changes addressed by native IDs. Read [composition](references/composition.md) for this shape and only the affected bindings. For new composition, validate the complete draft batch with `dl_editor_validate(drafts=...)`; carry a compiled recipe's `visual_contract` into item `presentation`. Supply a concrete calculation/meaning in each chart item's `hint`; a chart may await placement, but a finished dashboard cannot omit its widget hint. Use native `selector_group` for grouped Dataset/parameter controls. Retain raw snapshots for exact imports or documented adapter gaps.

Follow [authorized scope and delivery](references/authorized-scope.md) for mutations, continuation and completion across projects. For a visual or semantic choice, load the relevant part of [visualization decisions](references/decision-quality.md). For visible changes, check the affected rendered state with Browser read-only after API and applicable data checks; a correct readback alone does not prove correct layout. An API error or review-size rejection does not authorize switching dashboard edits to Browser, shell or an opaque payload. If the request is too large, use the supported compact delta through the same reviewed tool route. If that route is unavailable or fails, report the exact contract or access limitation; keep Browser read-only unless the user explicitly requests UI editing.

Route field/native chart changes to `datalens-dataset-wizard`, JavaScript runtime changes to `datalens-editor`, discovery to `datalens-inspect`, and backup/cleanup or standalone Page work to `datalens-maintenance`.

For unknown effects follow [repeat-effect recovery](references/authorized-scope.md#unknown-outcomes-and-repeat-effects): only proven non-application or separate informed repeat authorization permits another attempt. Failed reconciliation, absent inventory and a new operation_id do not make a retry safe.
