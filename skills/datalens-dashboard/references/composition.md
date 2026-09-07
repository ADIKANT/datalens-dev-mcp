# Dashboard composition contract

- Start from a fresh saved dashboard and apply only requested paths. Existing tabs, widgets, unknown fields, and manual `x/y/w/h` geometry are authoritative.
- Keep target and visual reference as separate objects. A reference may supply authoring defaults; it is never the update target.
- A selector declares parameter name, type, default, empty/select-all behavior, and every consumer. Remove stale widget-level overrides of that same parameter before publishing.
- Do not use reserved URL/runtime parameter names: `tab`, `state`, `mode`, `focus`, `grid`, `scale`, `tz`, `timezone`, `date`, `datetime`, `_action_params`, `_autoupdate`, `_opened_info`, `report_page`, `preview_mode`.
- A fixed semantic matrix status legend is not a dynamic series legend and remains visible. Cumulative comparison may intentionally overlap periods.
- Create object graphs in explicit `depends_on` order. There is no fixed 25-object ceiling and no claim of batch atomicity.
