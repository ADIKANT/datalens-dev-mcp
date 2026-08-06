# Dashboard Object Relations

`artifacts/dashboard_object_relations.json` is the implementation-plan and
validation surface for dashboard object dependencies.

## Represented Objects

- dashboard id placeholder and dashboard name
- dashboard type and layout blueprint
- pages/tabs
- tab-to-widget relations
- widgets, layout coordinates, title modes, and derived native metadata
- charts, chart routes, display titles, and title-contract hashes
- chart-to-chart relations
- selectors and selector target widgets/charts
- navigation relations
- dataset dependencies
- field dependencies
- calculated field dependencies
- dashboard-level filters

The schema is `schemas/dashboard-object-relations.schema.json`.

## Selector Requirements

Selectors must declare their targets explicitly:

```json
{
  "selector_id": "selector_segment",
  "param": "segment",
  "params": ["segment"],
  "label": "Segment",
  "labelPlacement": "left",
  "width": "94%",
  "targets": [{"target_id": "widget_001", "target_kind": "widget", "param": "segment"}]
}
```

Paired date controls declare and target both parameters:

```json
{
  "selector_id": "selector_period_from_period_to",
  "param_from": "period_from",
  "param_to": "period_to",
  "params": ["period_from", "period_to"],
  "label": "Period",
  "labelPlacement": "left",
  "width": "94%",
  "targets": [
    {"target_id": "widget_001", "target_kind": "widget", "param": "period_from"},
    {"target_id": "widget_001", "target_kind": "widget", "param": "period_to"}
  ]
}
```

Selector layout inherits the dashboard layout contract:

- labels are on the left
- widths are percentages
- row width total stays at or below 94 percent
- every declared selector parameter has a target and dashboard filter
- selector relations are included in the generated Markdown dashboard plan

Relations are emitted only from an explicit valid selector contract (or an
explicit legacy parameter supplied by a fixture). Requirements prose does not
create an implicit selector.

## Title Contract And Native Metadata

Wizard widgets normally carry `title_mode=native_title`:

```json
{
  "native_metadata": {
    "title": "Orders Trend",
    "hint": "Metric definition and source context.",
    "hideTitle": false,
    "enableHint": true
  }
}
```

Advanced Editor charts normally use `embedded_title`, while KPI cards use
`content_label`; both set `hideTitle=true` and render the exact accepted label
inside the protected runtime. A native inner tab header uses `tab_strip`.
Native and runtime title ownership may never be active at the same time. The
relation artifact is the traceable place to verify `title_contract.sha256`
before Safe Apply.

## Validation And Readback

`dl_validate_project` validates relation files when dashboard bundles exist.
`dl_readback_and_report` includes a compact object relation summary in readback
and deployment reports so manual checks can see what each selector affects.

Chart creation should not drop selector relations. If a new chart or selector is
created, update the relation file and the Markdown implementation plan in the
same step.
