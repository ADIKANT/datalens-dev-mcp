# Dashboard Payload Preflight

Dashboard payload preflight runs before live dashboard save paths. It validates
the JSON payload that will be sent to DataLens, not the separate
`dashboard_object_relations.json` planning contract.

The validator blocks:

- duplicate item ids anywhere in the payload;
- duplicate nested widget tab ids, including repeated legacy ids;
- missing or malformed nested tab ids;
- selector/control id collisions with widget or chart ids unless an existing
  global control is explicitly marked preserved;
- missing native title/hint metadata on new multi-tab blocks, while unchanged
  legacy widgets can be preserved when current dashboard context is supplied;
- inline Advanced Editor titles that duplicate dashboard native title/hint
  metadata;
- selector layout violations: label placement defaults to left, widths use
  percent units, and selector rows stay within a 94 percent budget;
- selector `impactTabsIds` values that reference tabs absent from the payload;
- invalid or mixed `autoHeight` policies in newly generated native-grid
  widgets, while unchanged saved legacy layouts remain warning-only;
- date-range selector regressions back to preset controls when the project
  contract requires a range control;
- debug/service widgets in publish layouts unless explicitly allowed by the
  project contract;
- stale `NO TABLE` style defaults when availability evidence says the source is
  available;
- missing selector/filter fields when the payload declares dependencies;
- unsafe DataLens technical identifiers.

Generated MCP payloads can call
`rewrite_duplicate_nested_tab_ids(payload)` before validation. Externally
supplied dashboard JSON fails fast with structured issue fields: `severity`,
`rule`, `path`, `message`, `object_type`, `duplicated_id`, and
`suggested_fix`.

Object id namespaces stay separate:

- DataLens widget id identifies the dashboard item.
- Nested tab id identifies a tab inside a widget or grouped block.
- Chart id identifies the Editor/Wizard object placed in a widget.
- Selector/control id identifies a dashboard control and should not be reused
  by charts or widgets.
- Display title/hint are visible metadata and are separate from technical
  technical names.
- Visible titles may keep human-readable punctuation such as `/`; technical
  `entry.name` and `data.name` values must use sanitized technical names.
