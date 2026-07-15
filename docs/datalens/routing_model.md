# DataLens Routing Model

Source trace: `AGENTS.md`, `docs/route-policy.md`, official DataLens API/docs extraction, `config/datalens_chart_param_matrix.json`, and `config/datalens_routing_model.json`.

The MCP router chooses the operation kind before it chooses a chart family.
This prevents Advanced Editor JavaScript from becoming the default answer for
dataset, connector, field, Wizard, or dashboard-relation work.

## Operation Kinds

| Operation kind | Route | Object kind | Use |
| --- | --- | --- | --- |
| `advanced_editor_chart` | `editor_advanced` | `editor_chart` | Explicit JavaScript or a registered capability gap. |
| `wizard_native_chart` | `wizard_native` | `wizard_chart` | Standard native chart creation across the canonical 16 visualization IDs. |
| `ql_explicit_chart` | `ql_explicit` | `ql_chart` | Direct QL request with explicit payload or fresh saved seed. |
| `dataset_operation` | `dataset` | `dataset` | Dataset, field, calculated field, measure, dimension, and aggregation changes. |
| `connector_operation` | `connector` | `connection` | Connector and connection setup before datasets. |
| `dashboard_relation_operation` | `dashboard_relation` | `dashboard` | Tabs, layout, selector relations, widget relations, and chart placement. |

The route registry is `config/route_selection_policy_v5.json`. Standard charts
use `wizard_native`; dedicated Editor routes cover registered gaps, specialized
tables, Markdown, and controls. QL read/create/update is explicit-only.
`wizard_map_native` is a compatibility alias for `geolayer`.

## Deterministic Decision Order

1. Preserve an existing technology and visualization ID from fresh saved readback.
2. Respect an explicit Wizard, JavaScript, or QL request when its gates pass.
3. Route connector wording to `connector_operation`.
4. Route dataset, field, calculated field, measure, dimension, and aggregation
   wording to `dataset_operation`.
5. Route selector/object/tab/layout relation wording to
   `dashboard_relation_operation`.
6. Route a registered JavaScript capability gap to its Editor route.
7. Route remaining standard chart requests to `wizard_native` using the
   visualization mapping in the policy registry.
8. If the request is only "make a chart" without business goal, metric, data shape,
   or action, return a targeted question instead of guessing.

Map requests default to `wizard_native/geolayer`. An explicit JavaScript map
request remains blocked unless a separately registered capability gap is added.

Removed charts are unreachable as creation families. Removed aliases either map
to an approved alternative or return `blocked_question` when the old chart needs
manual-review evidence.

QL is never selected by a vague SQL/chart request or as fallback. A direct QL
request returns `ql_explicit` and still requires approval provenance plus an
explicit payload or fresh saved seed.

## Dataset Validation

Chart routing should validate requested fields against a supplied dataset schema
when possible:

- `validated`: all required fields are present.
- `blocked_missing_fields`: required fields are absent and chart generation must
  stop with the missing field list.
- `schema_unavailable`: no schema was supplied; continue only with a visible
  assumption or request the schema.

Dataset creation and field definition are first-class prerequisites. Calculated
fields must be represented in dataset config, not hidden inside chart
`prepare.js`.
