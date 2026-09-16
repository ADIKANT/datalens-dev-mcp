# Editor authoring

The five Editor variants have different contracts. Native JavaScript table uses `table_node` and Config; Gravity uses `d3_node`; Advanced uses `advanced-chart_node`; Markdown uses `markdown_node`; selectors use `control_node`. Do not route all JavaScript work to Advanced.

For a new visual or requested redesign using a registered family, call `dl_authoring_defaults`, then `dl_compile_recipe` with typed bindings and presentation. The compile tool writes the full draft under private local state by default and returns a compact `draft_reference`; use that handle unchanged with `dl_editor_validate` or `dl_object_create`. For `dl_object_update`, put its `artifact_path` beside the target `object_type`, `object_id`, and fresh `expected_revision` in one change item; the server maps compiled tabs into saved data while preserving unrelated readback fields. A small existing-tab edit follows the addressed route below. Registered recipes own title, hint, tooltip, formatting, axes, labels, legend, comparison, geometry and states. Large renderer modules are packaged assets; do not read or reproduce them in prompts or output payloads. An explicit current requirement or reference has priority over project and user defaults.

Editor execution is source data, Prepare transformation, then rendering. Use valid source aliases and the exact tabs for the variant. Do not assume Node.js, `libs/sql/v1`, arbitrary npm packages, or browser APIs exist. Preserve arguments passed through `wrapFn`. A static check is reported as `static/source contract checked; live result not checked` until a real DataLens runtime read or host browser inspection proves the result.

Dataset-backed matrix, KPI, and weekly-total recipes accept `dataset_id`, exact field readback, and their documented role bindings. Their packaged source compilers call `Dataset.getDatasetRows`; selector-driven Dataset filters use the readback title with `type: "title"`, and the weekly recipe groups numeric metric rows into ISO-week columns and totals before rendering. Do not supply matrix-shaped rows to the weekly renderer or replace a live Dataset source with static `prepared_data` for acceptance.

Pure title, hint, spacing, color or layout changes do not require a Dataset query. A direct-source Editor chart must not receive a fictitious Dataset or a fabricated data-proof pass.

## Existing object to validation draft

`dl_object_get(view="full")` retains the provider object. Its `object.data` keys (`meta`, `params`, `sources`, etc.) are not validator filenames, and `object.type` is the observed subtype. Keep that full object separately; a typed static draft represents editable tabs, not all provider fields and not a replacement snapshot. Do not send raw `data` as `tabs`, change the subtype or fill missing tabs with fabricated empty source.

For a successful full read retained as `read`, this caller-side projection preserves tab text exactly and chooses only the actual variant's contract:

```javascript
store("editorBefore", read); // private full snapshot, including unknown provider fields
const object = read.object;
const allowed = {
  table_node: ["meta", "params", "sources", "prepare", "config"],
  d3_node: ["meta", "params", "sources", "prepare", "controls"],
  "advanced-chart_node": ["meta", "params", "sources", "prepare", "controls"],
  markdown_node: ["meta", "params", "prepare"],
  control_node: ["meta", "params", "controls"],
};
const names = allowed[object.type]?.slice();
if (!names) throw new Error("Unsupported Editor subtype: " + object.type);
if (object.type === "control_node" && "sources" in object.data) names.push("sources");
const tabs = Object.fromEntries(names.map(name => {
  if (typeof object.data[name] !== "string") throw new Error("Missing source text: data." + name);
  return [name === "meta" ? "meta.json" : name + ".js", object.data[name]];
}));
const draft = {variant: object.type, tabs};
store("editorDraft", draft);
// Edit only the requested tab in draft.tabs, then:
const result = await tools.mcp__datalens__dl_editor_validate({draft});
text(result.structuredContent ?? result);
```

Projected tabs, including Meta source aliases, remain verbatim. The full snapshot also retains provider fields outside the static variant contract: for example, a Table's extra raw `controls` field stays in the snapshot without becoming an unsupported `controls.js` validation tab. If an explicit `source_aliases` list accompanies your authoring draft, retain it too; do not infer or rename aliases from display labels. For a single Prepare edit, send only `patch: {data: {prepare: draft.tabs["prepare.js"]}}` with the exact target and fresh `expected_revision`. Preserve all other provider fields through the narrow update. Verify the changed tab and untouched bindings in saved readback, then apply the [publication and own-delta restore rules](../../datalens-dashboard/references/authorized-scope.md#saved-state-publication-and-restoration).

Validation proves the static contract only. For a runtime failure, distinguish JavaScript execution, an unresolved alias/source, a provider error, a valid empty query and an invalid KPI calculation. Do not hide upstream failure under a “no data” label. If the same shape/alias problem persists on a real object despite this mapping, report the exact path and observed shape before dispatch; do not weaken the subtype contract or introduce a new write route.

## HTML inside an Editor chart

Use the selected Editor runtime's supported `Editor.generateHtml`/table rendering contract and current source bindings. Diagnose empty Prepare output separately from invalid cell content or a render error. Standalone HTML Page iframe CSP, resource allowlists and parent-message protocol are not Editor rules. A standalone Page request belongs to the maintenance skill; do not migrate an existing Editor chart merely because it contains HTML.

## Exact reusable compositions

- `kpi_sparkline`: independent responsive KPI, uppercase body label and inline hint, current value plus rounded delta badge, large previous-value block, filled trend with missing-point gaps. Bind `metric`, `date`, `comparison` and either `source` or `prepared_data` (`value`, `previous`, `points` of date/value). Use `labels.precision` for fractional/currency metrics; counts default to zero decimals. Comparison method and dates come from the source; cumulative lag is not a previous non-overlapping window.
- `comparison_matrix`: version/status columns supply `key` and all six `headers` in release scope, release target, CI/IS, release status, assembly, version-type order. Rows supply label and cells with value/status plus optional provenance. Status keys: `noChange`, `hwChange`, `swChange`, `blChange`, `missing`, `manual_not_applicable`, `config_error`. Identical child labels remain separate across parent groups. Numeric current/previous rows remain a distinct comparison mode; never invent extra headers to pass them off as a version matrix. Give six headers and body sufficient height for scrolling.
- `weekly_totals_table`: preserve ordered groups, ISO week labels and manual height, with 132/82/96 default widths and bottom/right totals. For ratios, averages or distinct counts supply correct source-computed row, column and grand totals; summing aggregated cells is not valid.
- `period_series`: Advanced Editor line/bar period family, independent of native `time_comparison`. Bind `metric`, `date`, `comparison`, and source or prepared data with `categories`, `comparisonCategories` (or ranges), and `series`. Each series has `name`, `type` (`line`/`bar`), `color`, `values`, optional `comparisonValues`, `comparisonLegendName`, `format` (`integer`, `decimal1`, `decimal2`, `percent`), and explicit `summaryValue` when appropriate. Optional current/comparison ranges preserve partial-period semantics in hover. Missing/future points are null, not zero. Source owns cutoffs and alignment; the renderer does not infer business dates. Native/widget title ownership suppresses the body title.

A synthetic scenario may explicitly use prepared data. It proves composition, not live business-source connectivity. Inspect normal/compact viewport, hover, scroll, and saved/published runtime; successful compilation or a profile name is not visual acceptance.

Across recipes, preserve source semantics: NULL or unknown stays missing rather than zero; a KPI with no denominator remains undefined; polarity stays neutral unless declared; non-additive totals come from the source rather than summing cells; signed series retain negative observations and a zero baseline. Treat a historical fixed defect as current only after reproducing it on the active source/runtime.

## KPI and calendar inputs

KPI presentation uses `kpi.direction` (`higher_is_better`, `lower_is_better`, `neutral`), `kpi.delta_kind` (`relative`, `absolute`, `percentage_points`), and `kpi.value_scale` (`null`, `fraction`, `percent`). The same keys on the `metric` binding seed semantics; selected profile/reference values and explicit presentation overrides take precedence. Keep known accepted metric polarity explicit; unknown direction remains neutral. Relative delta is `(current - previous) / abs(previous)`; a zero base is undefined, never Infinity. Absolute delta retains metric units; percentage points respect fraction/percent scale. Preserve raw point precision when formatting body and tooltip.

The `date` binding accepts `mode` (`auto`, `calendar`, `temporal`, `ordinal`) and `granularity` (`day`, `week`, `month`). Known calendar grids use UTC boundaries (monthly points use month starts) and fill absent periods with null; filling the sparkline grid never recomputes the source KPI total. Irregular ISO dates use proportional elapsed-time spacing. Explicit `ordinal` comparisons retain their aligned positions. Do not connect gaps or replace signed observations with zero.

A shared renderer change belongs to its owning source project and affects its consumers. Establish that scope first, check the changed family on representative permitted consumers, and preserve unrelated bindings. Do not apply the shared-renderer delivery cycle to a local tab or metadata edit.
