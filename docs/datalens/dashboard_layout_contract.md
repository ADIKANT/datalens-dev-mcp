# Dashboard Layout Contract

## Contract Basis

The tab rule is a project-owned payload invariant covered by dashboard layout
tests and saved-readback validation:

- DataLens hides a widget-level tab strip when the dashboard widget item has
  only one `data.tabs[]` entry.
- To show inner tabs, one widget item must contain at least two `data.tabs[]`
  entries with distinct titles and chart IDs.
- `data.hideTitle: false` is required; `data.hideTitle: true` can hide the
  header area and tab strip.
- Saved and published `getDashboard` readback is the proof surface after live
  changes.

## Tab Rule

Related tabs that behave as one logical dashboard control or analysis area must
stay inside one widget object when DataLens requires an inner tab strip. Do not
split those inner tabs into separate widgets if they must share one widget
header, one layout slot, and one readback contract.

Required multi-tab widget shape:

```json
{
  "id": "attribute-check-table",
  "type": "widget",
  "data": {
    "hideTitle": false,
    "tabs": [
      {"title": "summary", "chartId": "<DL_CHART_ID>", "isDefault": true},
      {"title": "missing attributes", "chartId": "<DL_CHART_ID>", "isDefault": false}
    ]
  }
}
```

## Selector Layout Rule

- `labelPlacement` is always `left`.
- Control `width` is always a percentage string.
- One row may use up to 94 percent of the available width.
- Rows above 94 percent are invalid and must fail with a clear diagnostic.
- Rows below the budget are valid when the controls remain readable and aligned.
- Split dense selector rows instead of using pixel widths.
- Pixel widths are allowed only if a future DataLens API field requires pixels;
  that exception must be documented with the API field name and source.

The MCP helper `datalens_dev_mcp.pipeline.layout_contract` provides:

- `plan_selector_row_widths(names)` for deterministic percentage widths.
- `validate_selector_controls(controls)` for label/width/row checks.
- `validate_dashboard_widget_tabs(dashboard)` for inner-tab shape checks.

## Template Consequence

Selector templates and examples must include `labelPlacement: 'left'` and
percentage `width` values. Fallback generated single selectors use `width: '94%'`.

## Native Grid And Height Rule

- Native dashboard tabs use a 36-column grid and require a one-to-one mapping
  between item IDs and layout IDs.
- Peer overlap, out-of-bounds geometry, broken parents, and parent cycles are
  blockers.
- A newly generated layout also blocks non-boolean `autoHeight` and mixed
  `autoHeight=true/false` inside one mounted widget.
- Existing saved layouts keep those two auto-height conditions as warnings so
  an unrelated update can preserve legacy geometry; changed geometry still
  requires runtime viewport evidence.
- Conventional title, control, KPI, and table heights remain guidance rather
  than universal constants because real content and mounted width determine
  the final slot.

## Browser Viewport Evidence

- Layout and dashboard changes require browser checks at two or more distinct
  widths, including a compact desktop viewport at or below 1280 CSS pixels and
  a wide desktop viewport at or above 1366 CSS pixels.
- Every viewport check records positive CSS `width` and `height`,
  `device_pixel_ratio`, document width, overflow, scoped object IDs, and a
  hash-bound screenshot.
- Screenshot pixel dimensions must match
  `CSS viewport × device_pixel_ratio` within a two-pixel tolerance. A valid
  image header or hash alone does not prove that the requested viewport was
  captured.
- Horizontal overflow above two pixels, clipped or missing scoped objects, or
  a screenshot/viewport mismatch blocks browser-rendered evidence.

## Object Relation Link

Layout is not enough to define behavior. Dashboard assembly must also write
`artifacts/dashboard_object_relations.json` so every selector declares the
widgets/charts it affects, every chart declares dataset and field dependencies,
and the generated Markdown dashboard plan includes a selector-to-chart summary.

## Dashboard Type Blueprints

Dashboard type controls layout defaults before chart generation:

- `overview`: compact top selector row, KPI row, trend/comparison, detail or navigation.
- `self_service`: dense filter panel, summary, comparison/trend, detail table.
- `object_management`: status/owner filters, action queue, reason breakdown, object navigation.
- `alerts_mailing`: minimal filters, threshold summary, exception table, owner/action block.
- `analytical_tool`: method note, method-safe filters, primary analysis, supporting detail.
- `experiment_report`: cohort/period controls, hypothesis, cohort metrics, trend context, decision block.
- `project_ad_hoc`: scope filters, status strip, milestones, risk/action table, owner block.

All blueprints require native widget metadata for non-control widgets.
