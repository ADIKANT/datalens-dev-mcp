# Route Policy

The versioned source of truth is
`config/route_selection_policy_v5.json`. Request classification, object routing,
the chart parameter matrix, Wizard templates, and the golden gallery consume
that registry instead of maintaining independent route defaults.

## Deterministic Selection

1. For update, preserve the technology and visualization ID from fresh saved
   readback.
2. For create, honor an explicit Wizard, JavaScript, or QL request.
3. Select JavaScript only for a registered capability gap.
4. Otherwise select Wizard before any transport call.
5. Never retry a failed route through another technology.

Every route decision returns `route`, `visualization_id`, `selection_origin`,
`selection_reason`, and, for JavaScript, `capability_gap`.

## Creation Routes

- `wizard_native`: standard native chart creation and update through
  `createWizardChart` / `updateWizardChart`.
- `wizard_map_native`: compatibility alias accepted only as
  `wizard_native` + `visualization_id=geolayer`.
- `editor_advanced`: explicit JavaScript or a registered visual capability gap.
- `editor_table`: specialized grouped/pinned JavaScript table semantics;
  ordinary flat and pivot tables use Wizard.
- `editor_markdown`: dedicated Markdown objects.
- `editor_js_control`: dedicated JavaScript controls.
- `ql_explicit`: QL read/create/update after a direct user request; never an
  automatic route or fallback.

| Standard semantics | Wizard visualization ID |
| --- | --- |
| KPI and KPI with delta | `metric` |
| Flat table | `flatTable` |
| Pivot | `pivotTable` |
| Line and multiline | `line` |
| Area | `area`, `area100p` |
| Vertical/time columns | `column`, `column100p` |
| Horizontal bars | `bar`, `bar100p` |
| Combined time chart | `combined-chart` |
| Pie/donut | `pie`, `donut` |
| Scatter/bubble | `scatter` |
| Treemap | `treemap` |
| Map | `geolayer` |

Bubble requires a size role. Maps require geo evidence. A create with an
unknown visualization ID is blocked. An update may preserve an unknown ID only
from fresh saved readback; internal tokens are never guessed.

Wizard create prefers a fresh saved seed of the same visualization ID. The
seed must come from the saved branch and carry a fresh revision. Entry,
revision, and location identities are removed before create; unknown `data`
fields are preserved and dataset/field GUIDs are rebound. When no seed exists,
the committed canonical template is used. Canonical fixtures do not claim live
verification.

QL create/update requires `route=ql_explicit`, approval provenance with
`selection_origin=explicit_user_request`, and either an explicit payload or a
fresh saved QL seed. General prompt-to-QL generation and QL delete are closed.

High-level non-chart routes remain `connector_operation`, `dataset_operation`,
and `dashboard_relation_operation`. Also closed are `d3_node`, regular Editor
Chart, Gravity UI Charts, automatic QL selection, runtime route fallback,
guessed IDs, hidden destructive/permission writes, and blind writes. Explicit
removal of named legacy objects uses the separate `retire_legacy_objects`
project-live lifecycle. Publish remains governed by delivery intent and
safe-apply readback gates, not by route selection.
