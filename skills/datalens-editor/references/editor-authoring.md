# Editor authoring

For an unfamiliar recipe input, read `dl_authoring_defaults(family=recipe_id).recipe_contract`: its `bindings_schema` is used by the compiler, including nested `source` (`meta`, `sources_js`, `prepare_js`, optional `params`) and `direct_source`. Keep the three inputs distinct: typed create drafts go in `dl_object_create(drafts=...)`; static Editor validation uses `dl_editor_validate(draft={variant,tabs:{filename:source}})`; compiled update uses the unchanged `draft_reference.artifact_path` with an exact target and fresh `expected_revision`. Validate a compiled artifact with `dl_editor_validate(drafts=[draft_reference])`. A raw tab object is not a compiled recipe. Never edit the packaged renderer inside a compiled artifact to bypass source-drift validation.

The five Editor variants have different contracts. Native JavaScript table uses `table_node` and Config; Gravity uses `d3_node`; Advanced uses `advanced-chart_node`; Markdown uses `markdown_node`; selectors use `control_node`. Do not route all JavaScript work to Advanced.

For a new visual or requested redesign using a registered family, call `dl_compile_recipe` with typed bindings and presentation; it resolves authoring defaults itself. Use `dl_authoring_defaults` separately only when the effective choices or conflicts need inspection. The compile tool writes the full draft under private local state by default and returns a compact `draft_reference`; use that handle unchanged with `dl_editor_validate` or `dl_object_create`. For `dl_object_update`, put its `artifact_path` beside the target `object_type`, `object_id`, and fresh `expected_revision` in one change item; the server maps compiled tabs into saved data while preserving unrelated readback fields. A small existing-tab edit follows the addressed route below. Registered recipes own title, hint, tooltip, formatting, axes, labels, legend, comparison, geometry and states. Large renderer modules are packaged assets; do not read or reproduce them in prompts or output payloads. Follow the shared [presentation precedence](../../datalens-dashboard/references/composition.md#effective-presentation-and-native-selectors). Treat a styling choice explicitly requested from a reference as an explicit override; passing the reference alone does not elevate its styling above project or user choices.

Editor execution is source data, Prepare transformation, then rendering. Use valid source aliases and the exact tabs for the variant. Do not assume Node.js, `libs/sql/v1`, arbitrary npm packages, or browser APIs exist. Preserve arguments passed through `wrapFn`. A static check is reported as `static/source contract checked; live result not checked` until a real DataLens runtime read or host browser inspection proves the result.

Dataset-backed matrix, KPI, and weekly-total recipes accept `dataset_id`, exact field readback, and their documented role bindings. Their packaged source compilers call `Dataset.getDatasetRows`; selector-driven Dataset filters use the readback title with `type: "title"`, and the weekly recipe groups numeric metric rows into ISO-week columns and totals before rendering. Do not supply matrix-shaped rows to the weekly renderer or replace a live Dataset source with static `prepared_data` for acceptance.

For an ordinary KPI comparing the same measure across two date ranges, use `kpi_sparkline` with `dataset_id`, `fields`, `date.field_guid`, `metric.field_guid`, `comparison` (label/semantics), `value_mode: "aggregate"` and requested period ranges. For example, January 2026 versus December 2025 uses `periods: {current: {param_name: "current_range", default: ["2026-01-01", "2026-01-31"]}, previous: {param_name: "previous_range", default: ["2025-12-01", "2025-12-31"]}}`. Use the requested dates rather than copying these example defaults. Active period parameters are required BETWEEN ranges on the date field. The compiler shares the Dataset binding across the enabled trend and period totals; totals query the aggregate measure without a date dimension, preserving ratios/averages instead of summing daily cells. Row, window and LOD measures require an explicit source contract. Keep formula-derived units and `bindings.hint` accurate. The existing separate-current/previous-field `last` and explicitly additive `sum` modes remain available.

Shared filters use `selectors: [{param_name: "category", field_guid: "<readback GUID>", default: [], empty_selection: "all", operation: "IN"}]`; Dataset parameters use `dataset_parameters: [{id: "<parameter GUID>", param_name: "parameter", default: ["value"]}]`. Both period queries and trend receive the same filters and Dataset parameters. Reuse these bindings instead of custom Sources JS. Native All/Reset (`[""]`), absent/null and empty selections follow the declared `empty_selection=all|none|error`; zero and false remain values. Single/multi/range behavior follows the chosen filter operation. A blank string is reserved by this native control contract and cannot also identify a business category: retain source rows and use an explicitly agreed distinct category value where required. Do not silently remap business data or convert missing/failed totals to zero. The compiler returns a private artifact handle, so callers need only send bindings and inspect its compact summary.

Effective `comparison.enabled=false` removes the period KPI's previous query and parameter; `kpi.sparkline=false` removes the trend query and date processing. Full / no-comparison / value-only period cards use three / two / one queries. Only `periods.current` is mandatory when comparison is disabled; the date field remains required for WHERE even when absent from returning columns. `prepared_data` requires `value`, plus `previous` only for comparison and `points` only for sparkline. A valid current total without points is ready. The legacy last/additive-sum modes still need dated rows to compute their values. Options that can be enabled dynamically by custom code need the union of all reachable source requirements; a static recipe flag is not a runtime toggle.

### Explicit Dataset query needs

For an Editor recipe needing a different projection, grain, window, denominator or detail order, use the existing compile route with `dataset_id`, saved `fields`, and `dataset_source: {queries, prepare_js}`. Each query declares `alias`, its consumer `role`, `field_guids`, optional `selectors`, fixed `filters`, `dataset_parameters`, `sort` and `limit`. Selectors and parameters belong to each query; none are inherited from top-level selectors. This keeps a global denominator independent of selected groups. Sort entries use `{field_guid, direction: "asc"|"desc"}`; include the actual time and tie-breaker fields for bounded detail. `prepare_js` exports the chosen recipe's prepared-data shape using `Dataset.getDatasetRows({datasetName: alias})`. It remains explicit user code; the compiler does not infer which aliases it uses or rewrite it.

Use `dl_authoring_defaults(family=...).recipe_contract.bindings_schema` for the exact nested contract. The compact compile `summary.source_plan` shows declared aliases, roles, returning fields/aggregation, filters/parameters, sort and limits. Full generated tabs remain in `draft_reference.artifact_path`. `upstream_cost=unverified` is deliberate: a narrow outer Dataset request does not prove that inner SQL joins, DISTINCT, history or CTE work disappeared. Inspect the actual DataSetData request and generated SQL in Inspector; use read-only plans/metrics when available. Record unavailable physical scan metrics as unknown. There is no automatic cache or change of connection, RLS, credentials or physical source.

Choose needs from the calculation, not from a shared broad source template:

- Simple count/sum/coverage needs its aggregate and any actual denominator, without unused relations, history or freshness. NULL estimates and true zero stay distinct.
- Rolling distinct actors need the union of the actual 1/7/30-day window (and each compared window), not summed daily distincts. Daily series need their own window; rolling trends may need earlier observations. Preserve gaps before known history.
- Latency uses the requested daily quantiles without averaging them into period quantiles. Error rates and Apdex retain their source weights/counts; different metric families need different columns. A selected team or top-N does not redefine the global daily denominator.
- Relation metrics keep the real parent/child cohort, including children outside the parent date range and many-to-many deduplication. Index relations and interval prefix sums once where needed; retain workday boundaries. Keep these checks outside the dashboard UI.
- Query-log KPI totals, daily series, distinct accounts and ordered recent detail have different grains. Preserve the actual replicas/client classification and the requested limit/tie-breaker. Missing comparison history or load timestamps cannot be invented.

An unknown `source.sources_js` / `prepare_js` is preserved as custom code. Do not trim SELECTs, CTEs or JavaScript branches by regex or guess dependencies. Author a new narrow form only from an explicit calculation contract and verify its results. Unclear custom dependencies do not block a title, hint or color edit. Pure title, hint, spacing, color or layout changes do not require a Dataset query. A direct-source Editor chart must not receive a fictitious Dataset or a fabricated data-proof pass.

For a rolling window, a BETWEEN selector can include `window: {days: 7, offset_days: -7}` with `empty_selection: "error"`. Its parameter is a two-ISO-date array. Sources recomputes the inclusive UTC calendar window from the selected end on every execution; this example requests the previous disjoint week. A full rolling trend must declare the entire needed lookback, including the longest trend/comparison window, not just the initial UI dates. Time-of-day/business-timezone calculations keep their explicit custom source contract.

KPI tooltips omit raw diagnostic numbers by default; `tooltip.raw_values=true` is an explicit inspection option. Turning comparison off removes comparison reads/delta and Current/VS headers while preserving the current value's precision and date range.

### Portable period-series presentation

Set supported family overrides in `.datalens/authoring.json` instead of editing every Prepare. For example, `families.period_series` may contain `axes_gridlines: {x_labels: true, y_labels: false}` and `labels: {percent_precision: 0, small_percent: true, stack_totals: false}`. Axis labels are independent of value labels/gridlines. Defaults retain existing axis/total behavior; each project chooses its profile. Decimal series formats `decimal0` through `decimal6` apply to body and tooltip (for example Apdex 3, RPS 2, latency 1); percentage formatting never changes raw values, ratios or numeric sort. Positive shares below one percent may display `<1%`. Line labels use plotted numeric order and available space, not series-index offsets. Stacked values are not renormalized by the renderer.

These controls target `period_series`; existing horizontal bars, scatter and tables keep their technology and explicit custom renderer when no native option exists. Scatter coordinates/units and reference lines must remain readable. Heatmap columns remain available via scrolling. Category aliases/order/colors and domain-specific precision belong in project bindings/profiles, not universal source enums. Test changed shared renderers on representative allowed consumers at normal/narrow viewports; static validation or a local SVG is not published DataLens proof.

## Existing object to validation draft

`dl_object_get(view="full")` retains the provider object. Its `object.data` keys (`meta`, `params`, `sources`, etc.) are not validator filenames, and `object.type` is the observed subtype. Keep that full object separately; a typed static draft represents editable tabs, not all provider fields and not a replacement snapshot. Do not send raw `data` as `tabs`, change the subtype or fill missing tabs with fabricated empty source.

For a successful full read retained as `read`, this caller-side projection preserves tab text exactly and chooses only the actual variant's contract:

```javascript
store("editorBefore", read); // private full snapshot, including unknown provider fields
const object = read.object;
const allowed = {
  table_node: ["meta", "params", "sources", "prepare", "config", "controls", "activities"],
  d3_node: ["meta", "params", "sources", "prepare", "controls", "config", "activities"],
  "advanced-chart_node": ["meta", "params", "sources", "prepare", "controls"],
  markdown_node: ["meta", "params", "sources", "controls", "prepare"],
  control_node: ["meta", "params", "sources", "controls", "activities"],
};
const names = allowed[object.type]?.slice();
if (!names) throw new Error("Unsupported Editor subtype: " + object.type);
const tabs = Object.fromEntries(names.filter(name => name in object.data).map(name => {
  if (typeof object.data[name] !== "string") throw new Error("Missing source text: data." + name);
  return [name === "meta" ? "meta.json" : name + ".js", object.data[name]];
}));
const draft = {variant: object.type, tabs, validation_scope: "supplied_tabs"};
store("editorDraft", draft);
// Edit only the requested tab in draft.tabs, then:
const result = await tools.mcp__datalens__dl_editor_validate({draft});
text(result.structuredContent ?? result);
```

Projected tabs, including Controls, Activities and Meta aliases, remain verbatim.
Validate the exact tabs being written; never remove a supplied tab to make validation
pass. `validation_scope: "supplied_tabs"` checks only the supplied fragment and
reports its scope. New complete drafts use the default `complete_draft` contract;
provider response.required does not become a requirement for every narrow update.
Unchanged unknown fields stay in the full saved snapshot. Preserve explicit
`source_aliases`. A single Prepare edit uses `patch: {data: {prepare: draft.tabs["prepare.js"]}}`
with fresh `expected_revision`; verify it and untouched bindings in saved readback.
Use the [publication rules](../../datalens-dashboard/references/authorized-scope.md#saved-state-publication-and-restoration).

SDK 3.0.0 carries Table Controls, Table/Gravity Config and Markdown Sources/Controls.
Activities is documented only for Table, Gravity and Selector; the existing raw
update/import carrier preserves it. The typed create builder has no Activities
setter and returns a scoped unsupported error before dispatch. Do not discard it
or upgrade the SDK blindly. See the [compatibility matrix](../../../docs/testing/docs-api-compatibility.md).

### Native calendar inputs

Dataset selector bindings can explicitly set `date_input: "utc_calendar_date"`
or `"iso_datetime"`. They accept strict YYYY-MM-DD, ISO datetime with an explicit
timezone, and native `__interval_...`/`__relative_...` forms through
`Editor.resolveInterval`/`Editor.resolveRelative`. UTC calendar mode converts the
instant to its UTC date; ISO datetime mode retains its timezone. BETWEEN includes
both supplied boundaries. A calendar end date is not automatically the end of a
timestamp day: use the intended instant boundaries for timestamp fields. Rolling
`window` requires UTC calendar mode (or the existing two-date contract).

```json
{"param_name":"event_period","field_guid":"date-field-guid","operation":"BETWEEN",
 "empty_selection":"all","default":[],"date_input":"utc_calendar_date"}
```

Clear/All removes only this selector's filter when `empty_selection=all`; it does
not inject today, reset unrelated parameters or alter other source families.
For custom SQL, keep normalization in the project's existing source owner. Record
the actual `Editor.getParams()` input (for example an array containing
`"2026-09-29T00:00:00.000Z"`), chosen timezone and inclusive/exclusive boundaries;
resolve native intervals only when their prefix is present. Never parse arbitrary
strings as dates or truncate timestamps without an explicit calendar-date contract.
Trace user choice → actual control value → resolved interval → source filter → rows → visible label. A dynamic end must not retain an old fixed date; six calendar months must not become 180 days. Use the project's agreed week start, timezone and day boundary in both SQL and renderer, with explicitly fixed dates in local checks. Clear only the selected date filter, retaining category and independent controls. A local control remains local; group/global controls reach only their declared charts/tabs, with no hidden default excluding expected rows.
Check declaration, global defaults, impactTabs/aliases, normalized query/filter,
selected entity, rows and rendered output together. The fixed input's expected
counts are evidence for that input; live data needs a fresh baseline.

Validation proves the static contract only. For a runtime failure, distinguish JavaScript execution, an unresolved alias/source, a provider error, a valid empty query and an invalid KPI calculation. Do not hide upstream failure under a “no data” label. If the same shape/alias problem persists on a real object despite this mapping, report the exact path and observed shape before dispatch; do not weaken the subtype contract or introduce a new write route.

## HTML inside an Editor chart

Use the selected Editor runtime's supported `Editor.generateHtml`/table rendering contract and current source bindings. Diagnose empty Prepare output separately from invalid cell content or a render error. Standalone HTML Page iframe CSP, resource allowlists and parent-message protocol are not Editor rules. A standalone Page request belongs to the maintenance skill; do not migrate an existing Editor chart merely because it contains HTML.

## Exact reusable compositions

- `kpi_sparkline`: independent responsive KPI, metric label, widget-owned title and hint by default, current value plus rounded delta badge, large previous-value block, filled trend with missing-point gaps. Bind `metric`, `date`, `comparison` and either `source` or `prepared_data` (`value`, `previous`, `points` of date/value). Use `labels.precision` for fractional/currency metrics; counts default to zero decimals. Comparison method and dates come from the source; cumulative lag is not a previous non-overlapping window.
- `comparison_matrix`: version/status columns supply `key` and all six `headers` in release scope, release target, CI/IS, release status, assembly, version-type order. Rows supply label and cells with value/status plus optional provenance. Status keys: `noChange`, `hwChange`, `swChange`, `blChange`, `missing`, `manual_not_applicable`, `config_error`. Identical child labels remain separate across parent groups. Numeric current/previous rows remain a distinct comparison mode; never invent extra headers to pass them off as a version matrix. Give six headers and body sufficient height for scrolling.
- `weekly_totals_table`: preserve ordered groups, ISO week labels and manual height, with 132/82/96 default widths and bottom/right totals. For ratios, averages or distinct counts supply correct source-computed row, column and grand totals; summing aggregated cells is not valid.
- `period_series`: Advanced Editor line/bar period family, independent of native `time_comparison`. Bind `metric`, `date`, `comparison`, and source or prepared data with `categories`, `comparisonCategories` (or ranges), and `series`. Each series has `name`, `type` (`line`/`bar`), `color`, `values`, optional `comparisonValues`, `comparisonLegendName`, `format` (`integer`, `decimal1`, `decimal2`, `percent`), and explicit `summaryValue` when appropriate. Optional current/comparison ranges preserve partial-period semantics in hover. Missing/future points are null, not zero. Source owns cutoffs and alignment; the renderer does not infer business dates. Native/widget title ownership suppresses the body title.
- `heatmap`: Advanced Editor matrix with explicit `rows`, `columns`, `metric` bindings and a source or prepared data returning aligned `row_labels`, `column_labels`, `values` (at most 10,000 cells). The source owns grouping and aggregation; null means missing and zero remains a value. All column labels remain present, with horizontal scrolling when formatted cells cannot fit. `heatmap.color`, `heatmap.missing_label` and optional `geometry.minimum_width` come from the selected profile or reference.

A synthetic scenario may explicitly use prepared data. It proves composition, not live business-source connectivity. Inspect normal/compact viewport, hover, scroll, and saved/published runtime; successful compilation or a profile name is not visual acceptance.

Across recipes, preserve source semantics: NULL or unknown stays missing rather than zero; a KPI with no denominator remains undefined; polarity stays neutral unless declared; non-additive totals come from the source rather than summing cells; signed series retain negative observations and a zero baseline. Treat a historical fixed defect as current only after reproducing it on the active source/runtime.

## KPI and calendar inputs

KPI presentation uses `kpi.direction` (`higher_is_better`, `lower_is_better`, `neutral`), `kpi.delta_kind` (`relative`, `absolute`, `percentage_points`), and `kpi.value_scale` (`null`, `fraction`, `percent`). The same keys on the `metric` binding seed semantics; selected profile/reference values and explicit presentation overrides take precedence. Keep known accepted metric polarity explicit; unknown direction remains neutral. Relative delta is `(current - previous) / abs(previous)`; a zero base is undefined, never Infinity. Absolute delta retains metric units; percentage points respect fraction/percent scale. Preserve raw point precision when formatting body and tooltip.

The `date` binding accepts `mode` (`auto`, `calendar`, `temporal`, `ordinal`) and `granularity` (`day`, `week`, `month`). Known calendar grids use UTC boundaries (monthly points use month starts) and fill absent periods with null; filling the sparkline grid never recomputes the source KPI total. Irregular ISO dates use proportional elapsed-time spacing. Explicit `ordinal` comparisons retain their aligned positions. Do not connect gaps or replace signed observations with zero.

A shared renderer change belongs to its owning source project and affects its consumers. Establish that scope first, check the changed family on representative permitted consumers, and preserve unrelated bindings. Do not apply the shared-renderer delivery cycle to a local tab or metadata edit.

## Project choice, semantic checks and optimization

Use the [technology/source order](../../datalens-inspect/SKILL.md#technology-and-source-selection) before recipe selection and the [affected metric check](../../datalens-dashboard/references/decision-quality.md#affected-metric-check) before changing calculations. Direct SQL with JS selectors is appropriate for an explicitly established direct-source project; a reusable Dataset is appropriate for a shared metric model or standard Wizard view. Neither rule is a universal preference.

Optimize in this order: identify sources consumed by the visible element; remove unused queries/fields without changing meaning; aggregate at the needed grain while retaining requested detail; compare values and filters before/after; measure only when claiming speed. Preserve custom source contracts. Do not add diagnostic queries solely to generate a report or benchmark a label edit.

Separate query count, returned rows/bytes, source elapsed time, available physical scan metrics, and page loading/rendering. Reduced JSON does not establish reduced physical scanning, and one successful query does not establish dashboard speed. A speedup claim needs at least three comparable before/after measurement pairs on the same slice, recording cache state. Otherwise report simplification or response reduction, and keep KPI/detail/filter parity evidence.

## Affected visual verification

After a visual edit, inspect the affected element in Browser after API and applicable data checks. For a responsive recipe, compare a wide viewport and 420 px, scrolling to all required data and checking hover and legend interactions. Diagnose recipe renderer, dashboard geometry and native host separately. Do not patch host limitations with unsupported CSS or claim that a backend save fixed rendering.

Show a title once through its agreed owner. Hints explain the metric rather than saying done/calculated. Preserve manual heights and widths as project baselines, not universal defaults; tables must remain readable, multiline values accessible, and required columns retained through supported scrolling. Verify tooltip/legend meaning and NULL versus zero when relevant. A screenshot does not verify CSV/XLSX; check export separately only when requested.
