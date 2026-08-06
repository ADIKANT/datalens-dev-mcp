# Current DataLens Docs Reconciliation

Source update report: `reports/update_report.md` generated at `2026-07-29T17:38:13.358317Z`.
Applied delta report: `reports/update_report_2026-07-29.md` generated at `2026-07-29T17:38:13.358317Z`.

This file is a distilled policy matrix. It does not copy raw documentation pages into the repository.

## Corpus Counts

- Current pages: `653`.
- Current chunks: `5019`.
- Changed pages: `9`.
- New pages: `2`.
- Removed candidates: `0`.
- Failed page checks: `0`.
- OpenAPI operations/paths: `95` / `95`.
- Required validation checks OK: `True`.

## New Pages Covered

- https://docs.yandex.cloud/ru/ru/datalens/html-pages/index.md
- https://docs.yandex.cloud/ru/ru/datalens/html-pages/versioning.md

## Feature Policy Matrix

| Cluster ID | Classification | MCP surface | Server decision |
| --- | --- | --- | --- |
| `api_versioning` | `supported` | DataLens API client version policy | Keep auto pinned to the compiled OpenAPI version; permit explicit latest only for curated read-only calls. |
| `api_changelog_v2` | `supported` | request compiler and read-only RPC validation | Validate getEntries with v2 arrays, pageToken, and ignoreSharedEntries semantics. |
| `release_notes_2605` | `read_only` | dl_reference and feature policy | Index the release note as capability context without inferring new API routes. |
| `html_pages_lifecycle` | `supported` | html_page lifecycle planners, Safe Apply, readback, and local sandbox validator | Use create/get/update HTML Page methods through the ordinary guarded lifecycle. |
| `table_column_alignment` | `guarded_plan_only` | Wizard table and pivot payload planning | Preserve current per-column alignment and use only documented auto, left, center, or right values. |
| `dashboard_margins` | `guarded_plan_only` | dashboard payload preflight and safe apply | Preserve current dashboard margin fields and allow guarded save plans; do not strip unknown style fields. |
| `dashboard_widget_background` | `guarded_plan_only` | dashboard payload preflight and relation/layout validation | Preserve widget background settings; generate only when an explicit dashboard layout plan owns the widget. |
| `dashboard_rounding` | `guarded_plan_only` | dashboard payload preflight | Preserve rounding fields and keep decorative chart-body rounding out of Editor payloads. |
| `dashboard_background` | `guarded_plan_only` | dashboard payload preflight | Preserve dashboard background settings through safe apply. |
| `dashboard_hide_tabs` | `guarded_plan_only` | dashboard tab update planner | Preserve hide-tabs settings and do not infer tab visibility from local templates. |
| `dashboard_tabs` | `guarded_plan_only` | dl_plan_dashboard_tab_update | Append/replace tabs only through fresh-read guarded plans. |
| `dashboard_title` | `guarded_plan_only` | role-based dashboard title/hint policy | Renderer Visual Spec v5 assigns one owner through `title_mode`; native and runtime headers cannot coexist. |
| `dashboard_contents` | `guarded_plan_only` | dashboard layout validation | Treat contents widgets as dashboard structure; preserve through readback and safe apply. |
| `dashboard_ai_widget` | `unsupported_explicit` | reference and preservation only | Do not create AI widgets from MCP; preserve unknown AI widget payloads on fresh-read update. |
| `dashboard_ai_reference_tab` | `unsupported_explicit` | reference and preservation only | Do not create AI/reference tabs from MCP; preserve existing fields when updating other tabs. |
| `workbook_access_basic` | `unsupported_explicit` | reference only | Use DataLens or Yandex Cloud access management for workbook permission changes. |
| `workbook_access_advanced` | `unsupported_explicit` | reference only | Advanced access changes are outside this MCP server. |
| `embedded_objects` | `read_only` | dl_reference and object reads | Embedding docs are retained as reference; create/update embed routes are unsupported unless separately implemented. |
| `roles` | `read_only` | dl_reference | Roles are used for operator guidance and sanitized diagnostics. |
| `editor_methods` | `supported` | Advanced Editor validator and bundle generator | Supported methods feed the Editor runtime allowlist. |
| `editor_tabs` | `supported` | Advanced Editor bundle generator | Generated payloads use current tab contracts for sources, params, prepare, and config. |
| `editor_sources` | `supported` | Editor source validators and SQL diagnostics | Generated source SQL is statically linted and tied to source artifacts. |
| `editor_code_helper` | `read_only` | dl_reference | AI helper docs are reference-only for authoring guidance. |
| `editor_widgets_advanced` | `supported` | editor_advanced route | Advanced widgets use the supported custom chart route. |
| `editor_widgets_gravity_ui` | `unsupported_explicit` | dl_reference | Gravity UI Charts remain documented-reference only under local route policy. |
| `editor_cross_filtration` | `guarded_plan_only` | selector and relation planning | Cross-filtration informs selector wiring and relation validation. |
| `editor_notifications` | `supported` | Advanced Editor validator | Notification APIs are allowed only where current Editor runtime allows them. |
| `visual_table` | `supported` | wizard_native flatTable/pivotTable and specialized table validators | Ordinary flat and pivot tables use Wizard; grouped/pinned capability gaps use the specialized Editor table route. |
| `visual_indicator` | `supported` | VisualDecisionEngine and wizard_native metric | Indicator/KPI requires explicit metric semantics and comparator policy. |
| `visual_bar` | `supported` | VisualDecisionEngine and wizard_native bar/column routes | Bar charts are selected by task, data shape, cardinality, and metric semantics. |
| `visual_line` | `supported` | VisualDecisionEngine and wizard_native line route | Line charts require time/ordered data evidence. |
| `visual_area` | `supported` | VisualDecisionEngine and wizard_native area route | Area charts require additive semantics and appropriate series count. |
| `visual_normalized_area` | `supported` | VisualDecisionEngine and wizard_native area100p route | Normalized area is selected only for part-to-whole over time semantics. |
| `visual_pie_ring` | `supported` | VisualDecisionEngine and wizard_native pie/donut routes | Pie/ring remain available only for small-cardinality part-to-whole tasks. |
| `visual_heatmap` | `supported` | VisualDecisionEngine and editor_advanced route | Heat maps require two-dimensional categorical/date grid evidence. |
| `visual_map` | `guarded_plan_only` | wizard_native route with geolayer visualization | Maps use the Wizard-first geolayer contract and require validated geo evidence. |
| `visual_combined` | `supported` | VisualDecisionEngine and wizard_native combined-chart route | Combined charts require explicit axis/metric compatibility. |
| `visual_choropleth` | `guarded_plan_only` | wizard_native route with geolayer visualization | Choropleth uses the validated Wizard geolayer planning contract. |
| `dataset_cache_invalidation` | `read_only` | dl_reference and dataset diagnostics | Cache invalidation docs are reference-only unless a validated API method is present. |
| `dataset_data_model` | `supported` | dataset planners and guarded update validators | Dataset field/model changes are represented inside dataset payloads. |
| `dataset_versioning_drafts` | `unsupported_explicit` | dl_reference and dataset request validation | Explain draft/current-version behavior but do not invent draft or promotion request fields. |
| `dashboard_trends_preview` | `read_only` | dl_reference and browser QA guidance | Treat preview trends as temporary dashboard UI state, not as a persisted chart/dashboard payload. |
| `audit_entry_scopes` | `read_only` | read-only inventory and audit response projection | Preserve compute as inventory-only and artifact as an audit-only scope value. |
| `datalens_limits` | `read_only` | dl_reference and validators | Limits inform budgets and warnings. |
| `chart_inspector` | `import_only` | dl_diagnose performance evidence | Inspector/HAR evidence may be imported; timings are not fabricated. |
| `troubleshooting_errors` | `supported` | dl_classify_source_error and SQL diagnostics | Known errors feed structured classifier and remediation output. |

## Unsupported Or Reference-Only Decisions

- `release_notes_2605`: StarRocks, mailings, shared objects, roles, cache invalidation, and hidden tabs do not enable guessed mutations.
- `dashboard_ai_widget`: Unsupported route returns explicit policy instead of a guessed payload.
- `dashboard_ai_reference_tab`: Unsupported route remains explicit and tested.
- `workbook_access_basic`: Permission mutation is outside the MCP route contract.
- `workbook_access_advanced`: Permission mutation is outside the MCP route contract.
- `embedded_objects`: No embedding secret or embed write route is exposed by default.
- `roles`: Role docs do not enable permission mutation.
- `editor_code_helper`: MCP does not depend on DataLens UI AI behavior.
- `editor_widgets_gravity_ui`: No Gravity UI chart creation route is added.
- `dataset_cache_invalidation`: No cache mutation route is guessed.
- `dataset_versioning_drafts`: Ordinary updateDataset is not treated as draft promotion; requests need exact API evidence before mutation.
- `dashboard_trends_preview`: Preview is dashboard-only, is not saved, and is unavailable in embedded dashboards.
- `audit_entry_scopes`: Neither scope enables a guessed direct reader or lifecycle route; artifact is not a generic MCP object type.
- `datalens_limits`: Limit docs do not add new write routes.
- `chart_inspector`: Missing inspector evidence is reported as timing_unavailable.
