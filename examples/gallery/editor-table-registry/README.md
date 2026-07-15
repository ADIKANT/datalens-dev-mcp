# Example JavaScript Table Folder

Required files for `table_node`:

- `meta.json`
- `params.js`
- `sources.js`
- `prepare.js`
- `config.js`

Optional file:

- `controls.js`

Contract notes:

- This folder is a simple/pivot DataLens JavaScript Table on `editor_table` / `table_node`.
- `prepare.js` exports a table model with `head`, `rows`, and optional `footer`.
- `config.js` owns table configuration such as size, sorting, pagination, title, and row click behavior.
- Use `editor_advanced` / `advanced-chart_node` instead when the table must be a custom HTML/SVG renderer through `Editor.generateHtml(...)`.
- Do not add `Editor.generateHtml(...)` to `table_node` prepare code.

Hydrate the remote baseline first when this folder maps to an existing widget entry.
