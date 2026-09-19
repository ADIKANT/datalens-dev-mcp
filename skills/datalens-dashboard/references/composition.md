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
              "hint": "Sum of order revenue within the selected period and region.",
              "item_id": "revenue",
              "at": [0, 2, 12, 8]
            }
          ]
        }
      ],
      "settings": {
        "dependent_selectors": true,
        "hide_dash_title": true
      }
    }
  }
  ```

  Do not replace `kind` with `type` or split `at` into top-level `x/y/w/h` fields. Validate the complete draft batch before create.
- Start from a fresh saved dashboard and apply only requested paths. Existing tabs, widgets, unknown fields, and manual `x/y/w/h` geometry are authoritative.
- Keep target and visual reference as separate objects. A reference supplies structure and bindings below current visual policy; it is never the update target.
- A selector declares parameter name, type, default, empty/select-all behavior, and every consumer. A typed `external_selector` must repeat its parameter defaults in `defaults`; DataLens ignores external-control values that are absent there. Remove stale widget-level overrides of that same parameter before publishing.
- Do not use reserved URL/runtime parameter names: `tab`, `state`, `mode`, `focus`, `grid`, `scale`, `tz`, `timezone`, `date`, `datetime`, `_action_params`, `_autoupdate`, `_opened_info`, `report_page`, `preview_mode`.
- A fixed semantic matrix status legend is not a dynamic series legend and remains visible. Cumulative comparison may intentionally overlap periods.
- Create object graphs in explicit `depends_on` order. There is no fixed 25-object ceiling and no claim of batch atomicity.

## Compact edits to existing tabs

Use `dashboard_patch` in `dl_object_update` for existing native tabs. Read the
current saved identity, revision and affected records first. The server reads the
complete saved object, checks `expected_revision`, applies the addressed delta
and saves through the existing writer. It verifies the complete resulting tabs,
including untouched neighbors, against saved readback. The full array stays out
of the tool arguments.

```json
{
  "changes": [{
    "object_type": "dashboard",
    "object_id": "dashboard-id",
    "expected_revision": "observed-saved-revision",
    "dashboard_patch": {
      "tabs": [{
        "id": "overview",
        "items": {
          "update": [{"id": "revenue", "patch": {"data": {"title": "Revenue by month"}}}]
        },
        "layout": {
          "update": [{"i": "revenue", "patch": {"y": 4, "h": 10}}]
        },
        "connections": {
          "add": [{"from": "region-selector", "to": "revenue", "kind": "ignore"}]
        }
      }]
    }
  }],
  "operation_id": "dashboard-layout-edit"
}
```

IDs and the native item payload above are synthetic; inspect the actual widget
subtype before choosing its fields. `items` uses `id`, `layout` uses `i`, and
`connections` uses the ordered pair `from`/`to`. Each collection supports `add`
(complete new native records), `update` (identity plus a narrow `patch`), and
`remove` (ID strings, or `{ "from": "…", "to": "…" }` pairs). Adds append;
updates preserve position and unknown fields. Missing/ambiguous targets, existing
add identities and repeated identities in one request fail before dispatch.
Patches cannot change identity keys. Widget deletion does not cascade: include
the requested layout and connection removals explicitly.

A tab's `patch` supports `title`, `aliases` and `settings`. Mapping values merge;
explicitly supplied nested arrays replace their addressed value, so preserve
every required member when changing an alias group. This route does not add,
remove or reorder tabs. Do not combine it with `patch`, `artifact_path` or
`remove_global_params` in the same change. `dl_object_diff` accepts the same
`dashboard_patch` for a compact read-only preview. Save/readback and publication
remain separate steps with their existing revision and unknown-outcome guards.

## Effective presentation and native selectors

New typed dashboards resolve user/project defaults automatically. `dashboard.project_root`
selects the exact project; `dashboard.presentation` and item `presentation` are
explicit scoped overrides. Copy `draft.visual_contract` into the item when placing
a recipe. `visible_title` is canonical; legacy `title` objects normalize at their
own precedence layer. Conflicting aliases in one layer fail with their paths.

Defaults hide the page title, show each widget title, suppress the chart/body
header, and enable its native `tabs[].enableHint` with concrete `hint.text`.
Supply `item.hint` or `presentation.hint.text`; content-category names are not a
hint. Missing text fails before create. Standalone charts can remain pending
placement. Explicit owner/visibility changes remain supported; existing narrow
updates preserve their unrelated presentation and descriptions.

`kind: "selector_group"` uses the SDK's native group builder. For example:

```json
{
  "kind": "selector_group", "item_id": "filters", "at": [0, 0, 36, 2],
  "apply_button": false, "reset_button": true, "update_on_change": true,
  "members": [{
    "item_id": "region", "title": "Region", "dataset_id": "dataset-id",
    "field": {"guid": "region-guid", "title": "Region", "data_type": "string", "type": "DIMENSION"},
    "element": "select", "multiselect": true, "default_value": []
  }]
}
```

Use actual Dataset field readback. Manual members use `param_name` and `options`
instead of `dataset_id`/`field`. Members support SDK selector options, stable IDs,
`default_value`, `affects`, `hint`, and left titles by default. A date interval is
`{"start": "2026-01-01", "end": "2026-01-31"}`; add `relative: true` for SDK
relative intervals. An interval default enables range selection; explicit
`is_range: false` conflicts with it. Preserve wrapper `show_on_tabs`, apply/reset
settings and member order. Tab `aliases` is an array of field/parameter-name arrays;
`connections` contains `from`, `to`, optional `mutual` ignore edges. Empty
connections retain the native broadcast behavior. Chart `params` must not mask
selector defaults. External Editor selectors stay standalone: the provider does
not support them inside native groups.

For an affected selector/control, inspect the actual saved container and its layout representation. Check the sum of child widths/heights and all gaps against available geometry; checking each child separately is insufficient. Read exact field GUIDs and data types before choosing date/time operators.

For deleting only explicitly named `settings.globalParams` keys, use `dl_object_update` with `object_type="dashboard"`, `object_id`, fresh `expected_revision` and `remove_global_params=["synthetic_unused_key"]`. First inspect current bindings and usage; the server verifies the exact container and absence after saving. This route preserves neighboring parameters and settings. Do not send an entire dashboard for a single-key removal. For normal values use the existing narrow patch; for compiled Editor tabs use the verified artifact reference. A host refusal before dispatch proves no write was sent, but is not permission to bypass review with an opaque payload or shell write.
