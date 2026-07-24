# Editor Authoring

Editor bundles keep API tab payloads as strings.

- Advanced uses `meta.json`, `params.js`, `sources.js`, `controls.js`, `prepare.js`.
- Table uses `meta.json`, `params.js`, `sources.js`, `prepare.js`, `config.js`.
- Markdown uses `meta.json`, `params.js`, `sources.js`, `prepare.js`.
- JS controls use `meta.json`, `params.js`, `sources.js`, `controls.js`.

Do not put secrets in tabs, params, markdown, comments, or generated HTML.

## Versioned project profiles

The default route policy remains Wizard-first. A project that intentionally
standardizes every supported family on registered Editor templates can declare
a versioned profile in `.datalens-mcp.json`:

```json
{
  "authoring_profile": {"id": "standard_editor_v1"}
}
```

The same profile can be selected for one generation call with
`authoring_profile="standard_js"`. It resolves the semantic family through
`templates/datalens/standard_chart_templates.json`, selects the registered
Editor route and template directory, and returns SHA-256 identities for the
complete template set, selected assets, style contract, and compiled tabs.

This profile covers all 38 families currently registered for Advanced Editor,
Editor Table, Markdown, and JavaScript controls. The generated JavaScript comes
from the repository's standard templates and shared helpers; it is not rebuilt
from prompt text. An unknown family, a conflicting route, a changed asset set,
or an approximate fallback blocks generation.

The profile's template-set fingerprint is
`f1b2848350bc9dc0119149a50fdeb41bbd79faf0adee376f9ca5ab4f79bb4ed9`.
Changing any registered asset requires a reviewed profile version and updated
fingerprint. Native maps remain on the Wizard route and are not part of this
JavaScript-only profile.

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

## Renderer Visual Spec v3

New decisions emit `2026-07-23.renderer_visual_spec.v3`. It preserves v2 value,
formatting, responsive, hint, and layout contracts and adds:

- semantic color roles for success, failure, warning, neutral, focus,
  comparison, and a lighter distinct track;
- wrap-or-expand labels with ellipsis only by explicit request;
- one exact interval label per tooltip bucket;
- explicit comparator and profile-controlled KPI surface/border defaults.

Visual Spec v2 remains accepted for existing saved artifacts.
