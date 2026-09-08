# Dashboard composition contract

- A new typed dashboard uses `dashboard.tabs[].items[]`; every item has `kind` and `at: [x, y, width, height]`. Charts and external selectors use `chart_id` and `title` (values below are synthetic):

  ```json
  {
    "object_type": "dashboard",
    "client_ref": "dashboard",
    "name": "Overview dashboard",
    "dashboard": {
      "tabs": [
        {
          "title": "Overview",
          "tab_id": "overview",
          "items": [
            {
              "kind": "external_selector",
              "chart_id": "selector-id",
              "title": "Region",
              "item_id": "region-selector",
              "at": [0, 0, 36, 2],
              "defaults": {"region_filter": []}
            },
            {
              "kind": "chart",
              "chart_id": "chart-id",
              "title": "Revenue",
              "item_id": "revenue",
              "at": [0, 2, 12, 8]
            }
          ]
        }
      ],
      "settings": {
        "dependent_selectors": true,
        "hide_dash_title": false
      }
    }
  }
  ```

  Do not replace `kind` with `type` or split `at` into top-level `x/y/w/h` fields. Validate the complete draft batch before create.
- Start from a fresh saved dashboard and apply only requested paths. Existing tabs, widgets, unknown fields, and manual `x/y/w/h` geometry are authoritative.
- Keep target and visual reference as separate objects. A reference may supply authoring defaults; it is never the update target.
- A selector declares parameter name, type, default, empty/select-all behavior, and every consumer. A typed `external_selector` must repeat its parameter defaults in `defaults`; DataLens ignores external-control values that are absent there. Remove stale widget-level overrides of that same parameter before publishing.
- Do not use reserved URL/runtime parameter names: `tab`, `state`, `mode`, `focus`, `grid`, `scale`, `tz`, `timezone`, `date`, `datetime`, `_action_params`, `_autoupdate`, `_opened_info`, `report_page`, `preview_mode`.
- A fixed semantic matrix status legend is not a dynamic series legend and remains visible. Cumulative comparison may intentionally overlap periods.
- Create object graphs in explicit `depends_on` order. There is no fixed 25-object ceiling and no claim of batch atomicity.

## Recipe title and hint ownership

For a newly compiled recipe, pass `draft.visual_contract` as the chart item's
`presentation`. The typed builder maps `visible_title.owner="body"` or `"chart"`
to `show_title=False`, `"widget"` to `True`, and `"hidden"` or `visible=False`
to `False`. It transfers only enabled widget-owned `hint.text`; `hint.content`
contains generic content categories and is not native hint text. The KPI recipe
keeps its standalone hint in the body by default; an explicit widget-owned hint
is removed from its body renderer and placed in the widget.

`object_name` names the saved object. Item `title` supplies the native widget
label; the body heading comes from the recipe's `visible_title.text`. Explicit
item `show_title` and `hint` override the handoff, including `False` and `None`;
keep these consistent with the selected owner to avoid deliberate duplicates.
Without `presentation`, ordinary charts keep the native title default. A
`chart_id` alone cannot infer remote chart ownership. This path does not patch
existing dashboards or their manual presentation.

Canonical synthetic KPI example (the metric/date/comparison bindings below use
actual compiler keys; replace GUIDs with scoped Dataset readback when binding a
Dataset instead of this prepared fixture):

```python
from datalens_dev_mcp.sdk import compile_recipe

kpi = compile_recipe("kpi_sparkline", bindings={
    "object_name": "Orders KPI",
    "metric": {"field_guid": "orders", "label": "Orders", "unit": "count",
               "direction": "higher_is_better"},
    "date": {"field_guid": "order_day"},
    "comparison": {"field_guid": "previous_orders", "method": "previous_period",
                   "label": "Previous period"},
    "prepared_data": {"value": 12, "previous": 10, "points": [
        {"date": "2026-01-01", "value": 10}, {"date": "2026-01-02", "value": 12}]},
}, presentation={
    "visible_title": {"owner": "body", "visible": True, "text": "Orders"},
    "hint": {"owner": "body", "enabled": True, "text": "Completed orders"},
})["draft"]
item = {
    "kind": "chart", "chart_id": {"$object_ref": kpi["client_ref"]},
    "title": kpi["visual_contract"]["visible_title"]["text"],
    "presentation": kpi["visual_contract"], "at": [0, 0, 12, 8],
}
```

Place `item` in `dashboard.tabs[].items[]` after its chart dependency. Validate
and create the complete batch. For this example, the assembled widget hides its
native title and hint; the rendered body has one heading and one hint target.
