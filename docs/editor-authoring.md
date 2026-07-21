# Editor Authoring

Editor bundles keep API tab payloads as strings.

- Advanced uses `meta.json`, `params.js`, `sources.js`, `controls.js`, `prepare.js`.
- Table uses `meta.json`, `params.js`, `sources.js`, `prepare.js`, `config.js`.
- Markdown uses `meta.json`, `params.js`, `sources.js`, `prepare.js`.
- JS controls use `meta.json`, `params.js`, `sources.js`, `controls.js`.

Do not put secrets in tabs, params, markdown, comments, or generated HTML.

## Exact project profiles

The default route policy remains Wizard-first. A project that intentionally
standardizes every supported chart on JavaScript can declare a versioned
profile in `.datalens-mcp.json`:

```json
{
  "authoring_profile": {"id": "charging_v2_exact"}
}
```

The same profile can be selected for one generation call with
`authoring_profile="charging"`. It resolves aliases to `charging_v2_exact`,
selects the registered Editor route for the semantic family, embeds the
93,916-byte Charging renderer byte-for-byte, and returns the canonical runtime,
adapter, template-asset, and compiled-tabs SHA-256 values. The locked runtime
fingerprint is
`5f37bbd6a7012e90d0567787f006629019a852623b833eb112debe5f8f50ebf3`.

The first profile version registers exact adapters for KPI value/delta/
sparkline cards, single and multi-line charts, vertical time bars, combined
time charts, and single/grouped horizontal bars. An unregistered family or a
conflicting route is blocked; the server does not substitute the normal MCP
template or invent an approximate fallback. Adding another family requires a
new reviewed adapter and updated fingerprints.

This contract captures the reusable Charging/DATA-5211 authoring pattern, not
their business SQL or private data. Maps remain on the native Wizard route and
therefore require a project without the JavaScript-only profile.
