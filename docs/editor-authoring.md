# Editor And Dashboard Authoring

Editor bundles keep DataLens tab payloads as strings.

- Advanced Editor uses `meta.json`, `params.js`, `sources.js`, `controls.js`, and `prepare.js`.
- Editor Table uses `meta.json`, `params.js`, `sources.js`, `prepare.js`, and `config.js`.
- Markdown uses `meta.json`, `params.js`, `sources.js`, and `prepare.js`.
- JavaScript controls use `meta.json`, `params.js`, `sources.js`, and `controls.js`.

Do not put secrets in tabs, params, markdown, comments, or generated HTML.

## Canonical authoring profile

Create and full-redesign generation defaults to `standard_dashboard`.
`strict_dashboard`, `standard_dashboard`, and `registered_dashboard` are aliases
for the same profile. It is a dashboard contract, not an instruction to convert
every chart to JavaScript.

The profile performs route selection first:

1. preserve the saved technology and visualization for an update;
2. honor a direct Wizard, Editor, or QL request;
3. use Editor for a documented capability gap;
4. otherwise keep standard KPI, table, line, area, column, bar, combined,
   pie/donut, scatter/bubble, treemap, and map charts on Wizard;
5. never use QL unless the user requested QL directly.

For selected Editor objects, the same `standard_dashboard` profile applies
the current template registry, Renderer Visual Spec, and a checksum-locked
neutral runtime. The query and row normalization may vary, but the renderer,
typography tokens, title chrome, and protected layout code may not be
rewritten.

There is only one executable built-in contract. Historical profile names are
accepted as input aliases, immediately normalized to `standard_dashboard`,
and never select historical assets or behavior. A saved Editor object keeps
its technology during an update, but its generated bundle is rebuilt and
attested with the current contract. A project-local descriptor cannot override
a reserved built-in alias.

## Renderer Visual Spec

Each generated component has top-level `authoring_profile`,
`editor_render_profile`, `render_contract_id`, and `title_mode` fields.
The title contract selects exactly one owner:

| Mode | Use |
| --- | --- |
| `embedded_title` | An Editor chart renders the exact title and hint in the protected runtime; native title is hidden. |
| `content_label` | A KPI renders its label inside the card; there is no separate header. |
| `tab_only` | The dashboard tab is the only visible title. |
| `native_title` | Wizard and native table metadata own the title. |
| `tab_strip` | A native header exposes an inner multi-tab switcher. |

Native and runtime title or hint ownership cannot coexist. `display_title` is
an acceptance value and cannot be replaced with a technical entry or widget
name.

The exact renderer includes reusable KPI, line/area, vertical and horizontal
bar, comparison-context, legend, tooltip, plot-inset, and horizontal-scroll
adapters. The bundle records runtime, adapter, selected asset, compiled tabs,
render profile, and composite hashes.

## Dashboard dashboard composition

`dl_generate_editor_bundle` accepts a `dashboard_composition` object and writes
a hash-bound skeleton. A batch composition declares:

- semantic tabs and rows on a 36-column grid;
- an exact mount → tab → widget relationship for every component;
- equal heights for neighboring blocks and `gap_after=0` unless a spacer is
  explicitly declared;
- no more than three standard KPI cards per row;
- `12×8` sparkline KPI and `12×6` compact KPI geometry;
- a four-card `9`-column row only with an explicit override and successful
  browser proof;
- comparison-context height 1–3 according to its actual line count;
- table guards for constant sticky columns, blank group headers, and clipped
  labels without a short display label.

A `selector_group` contains one or two ordered rows. Labels stay on the left,
each row uses exactly 94 percent width, changes apply immediately, and no Apply
button is rendered. One row has native height 2 and two rows have height 3. A
blank multiselect means all values; Clear must keep it blank and must not
restore a default. A neighboring load-date block uses the same height and
vertical alignment.

## Batch generation

Generate the dashboard in one call:

```json
{
  "authoring_profile": "strict_dashboard",
  "chart_specs": [
    {
      "widget_id": "summary_metric",
      "route": "wizard_native",
      "dataset_alias": "main",
      "columns": ["metric_value"]
    },
    {
      "widget_id": "custom_ranking",
      "route": "editor_advanced",
      "dataset_alias": "main",
      "columns": ["category", "metric_value"],
      "title_mode": "embedded_title"
    }
  ]
}
```

`chart_specs` accepts at most 100 unique widgets. Full bundles and tabs stay in
artifacts; the MCP response contains bounded statuses, paths, and hashes. If
`dashboard_composition` is omitted, the server builds the safe canonical skeleton; an
explicit composition must declare all tabs, rows, and widgets. A
comparison batch starts with its date selector and contains exactly one
structured comparison-context block.

## Final payload attestation

`dl_validate_project` rebuilds the actual final payload instead of trusting a
separate compiler output. It writes `final_payload_attestation` containing:

- canonical and actual routes;
- protected runtime and title-contract hashes;
- selector and composition hashes;
- hashes for every dashboard tab and component payload;
- the complete dashboard payload hash.

Validation reads materialized Editor tabs again, so rewriting `prepare.js` or
another protected tab is detected. A Wizard-to-Editor substitution, unattested
payload, create/redesign, or any post-validation title, selector, runtime,
layout, or payload change blocks Safe Apply and requires validation again.

Project-local execution commands cannot replace the protected composition path
for `standard_dashboard`; attested payload planning and Safe Apply own the
final request.

## Browser QA and delivery

The generated QA plan is bound to dashboard ID, saved/published revision,
final-attestation hash, composition hash, and payload hashes. It checks every
tab at its top and after full scroll at 720, 1200, and 1440 CSS pixels.

The pass verifies title/hint ownership, selector labels and width, Clear and
blank-multiselect behavior, equal row heights, undeclared gaps, KPI density,
clipping and useful sticky columns, internal scroll, tooltip, legend,
comparison context, visible series, lazy initialization, and runtime/network
errors.

A dashboard publish action requires a successful matching `qa_attestation`
with hashed browser evidence for the exact saved revision selected for publish.
Safe Apply publishes only that revision and verifies the published readback.
Published browser evidence for the same revision is then required before the
delivery state can become `done`.

Dashboard composition emits the native DataLens `widget.data.tabs[]` payload shape.
Its `operation` selects a schema-valid `CreateDashboardV1Args` or
`UpdateDashboardV1Args` envelope; the exact display title lives in dashboard
metadata while the technical `entry.name` stays a safe lowercase identifier.
The final attestation preserves every mount-to-chart binding: changing or
swapping a nested `chartId` after validation is blocking, even when geometry
and visible titles remain unchanged.

## Project-local exact profiles

A project may bind a reviewed custom Editor registry with `id`,
`descriptor_path`, and `descriptor_sha256`. The descriptor and every dependency
must remain inside the project root. It cannot add technologies, bypass the
canonical route decision, alter protected runtime after validation, or enable
fallback. Path escape, changed hashes, route conflicts, and missing families
block generation.
