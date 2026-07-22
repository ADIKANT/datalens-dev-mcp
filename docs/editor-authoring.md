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
