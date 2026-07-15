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
- One row must total exactly 96 percent.
- Rows above 96 percent are invalid and must fail with a clear diagnostic.
- Rows below 96 percent are also invalid because they create inconsistent control alignment.
- Split dense selector rows instead of using pixel widths.
- Pixel widths are allowed only if a future DataLens API field requires pixels;
  that exception must be documented with the API field name and source.

The MCP helper `datalens_dev_mcp.pipeline.layout_contract` provides:

- `plan_selector_row_widths(names)` for deterministic percentage widths.
- `validate_selector_controls(controls)` for label/width/row checks.
- `validate_dashboard_widget_tabs(dashboard)` for inner-tab shape checks.

## Template Consequence

Selector templates and examples must include `labelPlacement: 'left'` and
percentage `width` values. Fallback generated single selectors use `width: '96%'`.

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
