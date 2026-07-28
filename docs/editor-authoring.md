# Editor Authoring

Editor bundles keep API tab payloads as strings.

- Advanced uses `meta.json`, `params.js`, `sources.js`, `controls.js`, `prepare.js`.
- Table uses `meta.json`, `params.js`, `sources.js`, `prepare.js`, `config.js`.
- Markdown uses `meta.json`, `params.js`, `sources.js`, `prepare.js`.
- JS controls use `meta.json`, `params.js`, `sources.js`, `controls.js`.

Do not put secrets in tabs, params, markdown, comments, or generated HTML.

## Versioned authoring profiles

The default route policy remains Wizard-first. A project that intentionally
standardizes every supported family on registered Editor templates can declare
a versioned profile in `.datalens-mcp.json`:

```json
{
  "authoring_profile": {"id": "standard_editor_v2"}
}
```

The same profile can be selected for one generation call with
`authoring_profile="strict_dashboard"`. `standard_dashboard` and
`registered_dashboard` are equivalent aliases. It resolves the semantic family
through `templates/datalens/standard_chart_templates.json`, selects the
registered Editor route and template directory, resolves
`standard_dashboard_v1`, compiles the exact render contract into the tabs, and
returns SHA-256 identities for the template set, selected assets, render
profile, effective family adapter, and compiled tabs.

This profile covers all 38 families currently registered for Advanced Editor,
Editor Table, Markdown, and JavaScript controls. The generated JavaScript comes
from the repository's standard templates and shared helpers; it is not rebuilt
from prompt text. Each family is explicitly mapped to a registered adapter.
An unknown family, a conflicting route, a changed fingerprint, an inapplicable
override, or an approximate fallback blocks generation.

`standard_editor_v2` retains the reviewed template-set fingerprint
`0f52998c57443651845ab73718df1669d01c5b5e87d10e0bf6bd29d6ee4cd4d4`.
Its render profile is separately fingerprinted, and each resolved family plus
bounded overrides receives a `composite_sha256`. Changing a registered asset or
render token requires a reviewed profile version and updated fingerprint.
Native maps remain on the Wizard route and are not part of this JavaScript-only
profile.

`standard_editor_v1` remains available for compatibility. Its aliases are
`standard_editor`, `standard_js`, and `registered_editor`; it reuses the exact
registered templates but does not apply the v2 cross-chart render compiler.

## Exact `strict_dashboard` render contract

`standard_editor_v2` upgrades generated decisions to
`2026-07-28.renderer_visual_spec.v4` and binds the result to the immutable
`standard_dashboard_v1` tokens:

| Area | Exact default |
| --- | --- |
| Responsive scale | Minimum chart viewport `280 x 160`; KPI adapter `280 x 96`; compact below `720` px |
| Shell | Compact vertical/horizontal padding `9/10` px and gap `7` px; normal padding `11/13` px and gap `9` px |
| Font | `Inter`, then `Arial`, then `sans-serif` |
| Typography | Title `16/20` compact and `17/21` normal; body, axis, legend, and tooltip `12/16`; table `12/17` |
| KPI | Padding `11 11 7 11` px; label `12/15`; value `31/34` compact and `34/38` normal at weight `750`; visible marked value; height `88..112` px with `96` px preferred |
| KPI surface | Transparent background; zero border, radius, outline, and shadow |
| Selector | Left label, immediate update, no Apply button, height `44` px, each control at most `94%`; period first when present; one row targeting `95%` aggregate width; blank multiselect means all |
| Comparison context | Exactly one shared text block below selectors when comparison is enabled, none otherwise; method, selected range, and comparison range are required |
| Legend | One shared typography token across a chart; default and compact are `12/16` |
| Tooltip | Native owner, normalized period values, comparison labels only in comparison mode, no empty comparison period, maximum width `340` px, padding `10/12` px, flat surface, and no redundant row-title tooltip |
| Horizontal rank | Label `184` px, value `106` px, preferred bar `234` px, minimum row `32` px, row gap `4` px, bar radius `0.75` px, wrapped labels, stable secondary sort |
| Scroll variant | Stable scrollbar gutter and `4` px right padding |

The semantic defaults are primary `#2B75E2`, success `#6CBF84`, failure
`#E57373`, and comparison `#8A919C`. Browser QA also requires tooltip outline
and shadow to be absent.

Only three bounded override dimensions are accepted:

- `density`: `compact` or `comfortable`;
- `legend_typography`: `compact` (`12/16`) or `readable` (`14/18`);
- `horizontal_adapter`: `generic` or `scroll`, only for families that declare
  that override;

Tooltip ownership is fixed to `native`. A `renderer` request fails closed until
a registered adapter emits and validates exactly one renderer-owned tooltip
shell.

Overrides select registered tokens; they cannot supply free-form CSS,
typography, spacing, or geometry. The compiled bundle records the base tabs
hash, compiled tabs hash, compiler version, render profile hash, adapter IDs,
and composite contract hash.

## Batch generation

Generate a dashboard's Editor widgets in one `dl_generate_editor_bundle` call
with `authoring_profile="strict_dashboard"` and `chart_specs`. The persisted
chart decisions remain authoritative; batching does not bypass route,
requirements, source, or family validation.

```json
{
  "authoring_profile": "strict_dashboard",
  "chart_specs": [
    {
      "widget_id": "summary_metric",
      "dataset_alias": "main",
      "columns": ["metric_value"]
    },
    {
      "widget_id": "category_ranking",
      "dataset_alias": "main",
      "columns": ["category", "metric_value"],
      "render_overrides": {"horizontal_adapter": "scroll"}
    }
  ]
}
```

Each item may contain `widget_id`, `route`, `dataset_alias`, `columns`,
`selector_contract`, `dataset_readbacks`, `render_overrides`, and a structured
`comparison_context` for `md_methodology_block`. Shared
`render_overrides` are merged with item overrides. The list is non-empty,
supports at most 100 widgets, rejects duplicate IDs and unknown fields, and is
mutually exclusive with `html_page`. Per-widget generation arguments are not
accepted alongside `chart_specs`.

When a strict batch enables comparison, its first `chart_spec` must be a
`date_range_selector`, and exactly one `md_methodology_block` must provide
non-empty `comparison_context.method`, `selected_range`, and
`comparison_range`. The server renders those fields into one shared period
block and binds its exact widget ID into browser QA. Missing, duplicate, or
misordered comparison context blocks fail before any widget bundle is written.

The call writes each complete bundle, a batch manifest, and one combined
browser QA plan. The inline response contains only the batch counts, bounded
per-widget status, paths, and hashes; `full_bundles` is `artifact_only`.

## One-pass browser QA and delivery

The generated browser QA plan is immutable and hash-bound. Execute it once:

1. navigate once;
2. evaluate both `1200 x 900` and `1440 x 900` viewports in one batch;
3. capture one screenshot per viewport in one batch.

The maximum browser-call budget is three. The evaluation is read-only and
forbids DOM mutation, reload loops, and exploratory retries. It checks expected
objects, runtime error markers, overflow and clipping, KPI surfaces, legend
typography, selector geometry and behavior, comparison-context cardinality,
its runtime placement directly below the selector group and before KPI/chart
content, tooltip owner and surface, stable scrollbar gutters, and redundant
native row-title tooltips. Results and screenshots use the artifact naming plan
in the QA artifact.

After local validation and payload planning, create one target-locked safe-apply
plan and call `dl_execute_safe_apply` once. That executor owns group save,
saved readback, publish preflight, publish from verified saved state, and
published readback. Do not split the normal path into per-object executors or a
second publish plan; `dl_create_publish_from_saved_plan` is only for resuming a
previously stopped saved state.

## Project-local exact profiles

A project can bind its own reviewed template registry without modifying the
installed package:

```json
{
  "authoring_profile": {
    "id": "project_style_v1",
    "descriptor_path": "profiles/project_style_v1/profile.json",
    "descriptor_sha256": "<SHA256>"
  }
}
```

The descriptor uses
`2026-07-23.project_authoring_profile.v1`, declares supported Editor routes,
the project-relative family registry, `fallback_policy: "block"`, and the
SHA-256 of the complete registry/template/shared-asset set. Both the descriptor
and every referenced asset must resolve inside the project root. Path or
symlink escape, a changed hash, a route conflict, or a missing family blocks
generation.

Project templates are loaded exactly and support only bounded substitutions for
the widget ID, title, registered variant, and renderer Visual Spec. The
generated bundle records descriptor, template-set, selected-asset, and compiled
tab hashes.

## Renderer Visual Spec

`standard_editor_v2` emits `2026-07-28.renderer_visual_spec.v4`. It preserves
the semantic value and formatting fields, then binds scale, typography,
spacing, KPI, legend, selector, comparison, and tooltip fields to the resolved
render contract. Any conflicting inline legend typography, multiple tooltip
owners, KPI surface/content drift, selector order or geometry drift, tooltip
comparison-mode drift, or comparison-block cardinality drift blocks generation.

`standard_editor_v1` continues to emit
`2026-07-23.renderer_visual_spec.v3`. It preserves v2 value, formatting,
responsive, hint, and layout contracts and adds:

- semantic color roles for success, failure, warning, neutral, focus,
  comparison, and a lighter distinct track;
- wrap-or-expand labels with ellipsis only by explicit request;
- one exact interval label per tooltip bucket;
- explicit comparator and profile-controlled KPI surface/border defaults.

Visual Spec v2 and v3 remain accepted for existing saved artifacts; the strict
v2 authoring profile upgrades new generated bundles to v4.
