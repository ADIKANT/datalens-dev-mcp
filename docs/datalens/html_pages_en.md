# HTML generation for DataLens

[Русский](html_pages.md)

The server keeps two incompatible HTML contracts separate:

- `Editor.generateHtml(arg)` creates allowlisted markup inside an Advanced
  Editor chart. Plain strings are escaped; tags, attributes, URLs, and theme
  values follow the Editor contract.
- A standalone HTML page is a complete UTF-8 document for an isolated iframe.
  It is neither a chart nor an `Editor.generateHtml` call.

## Fast path

Pass `html_page` to the existing `dl_generate_editor_bundle` tool:

```json
{
  "project_root": "/absolute/project",
  "widget_id": "quality_report",
  "html_page": {
    "title": "Quality report",
    "lang": "en",
    "summary": "Synthetic example",
    "body_html": "<main class=\"dl-page\"><h1>Quality</h1><div id=\"app\"></div></main>",
    "style_css": "#app{display:grid;gap:12px}",
    "script_js": "document.getElementById('app').textContent=String(window.datalensPage.data.value);",
    "data": {"value": 100}
  }
}
```

The response contains only the path, byte count, SHA-256, and validation
summary. It does not return the HTML inline, so MCP response size stays
bounded. The document is written to
`artifacts/html_pages/<widget_id>.html`.

Validate it again through the same runtime validator:

```json
{
  "project_root": "/absolute/project",
  "artifact_paths": ["artifacts/html_pages/quality_report.html"]
}
```

`dl_validate_editor_runtime_contract` detects `.html` automatically. The hard
limit is 10 MiB per document and the authoring target is at most 5 MiB.

## Sandbox contract

The default generator is self-contained and includes:

- `theme` and `lang` query-parameter handling;
- safely embedded JSON at `window.datalensPage.data`;
- `EXPORT` and `OPEN_URL` parent `postMessage` helpers;
- responsive CSS without an external dependency;
- an early UTF-8 charset declaration.

Strict validation blocks author-supplied CSP, nested `iframe`, `object`,
`embed`, `form`, and `base` elements, persistent storage, cookies, network
APIs, workers, dialogs, popups, and parent navigation. CDN origins documented
by the public skill are allowlisted explicitly; generated pages need none.

## Publishing

The current DataLens Public API does not document an RPC or request/response
schema for creating or uploading a standalone HTML page. The server therefore
authors and validates a local artifact, does not guess an upload method, and
does not put this artifact into Safe Apply. The result reports
`publication.status=local_artifact_only`.

Sources:

- [official `Editor.generateHtml` documentation](https://yandex.cloud/ru/docs/datalens/charts/editor/methods#gen-html);
- [public `datalens-html-pages` skill](https://github.com/datalens-tech/datalens-skills/tree/8fbb3aabac6b09d4c44f053fa63affea1dc386f7/skills/datalens-html-pages);
- [allowlist HTML generator implementation](https://github.com/datalens-tech/datalens-ui/tree/f581b7c31d6e9189ebeb1e1632b5fe7570534fb8/src/ui/libs/DatalensChartkit/modules/html-generator).
