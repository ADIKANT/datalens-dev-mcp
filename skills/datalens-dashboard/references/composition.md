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
