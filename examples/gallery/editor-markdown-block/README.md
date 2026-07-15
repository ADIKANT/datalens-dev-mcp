# Example Markdown folder

Required files for `markdown_node`:

- `meta.json`
- `params.js`
- `sources.js`
- `prepare.js`

Optional synthetic file the live-ops layer may create during export or update when needed:

- `controls.js`

Contract notes:

- This folder is a DataLens Markdown visual on `editor_markdown` / `markdown_node`.
- `prepare.js` exports a Markdown model: `module.exports = {markdown}`.
- Do not add `config.js`.
- Do not use `Editor.wrapFn(...)` or `Editor.generateHtml(...)`; those belong to `editor_advanced`.

Hydrate the remote baseline first when this folder maps to an existing widget entry.
