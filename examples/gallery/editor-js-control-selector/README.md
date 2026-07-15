# Example selector folder

Required files for `control_node`:

- `meta.json`
- `params.js`
- `sources.js`
- `controls.js`

Forbidden files for selectors:

- `prepare.js`
- `config.js`

Contract notes:

- `select` controls must use `content: [{title, value}]`; do not use legacy `values` / `text`.
- Every selector `value` must be string-normalized, even when the source column is numeric.
- Dynamic selectors should repair invalid current params in `controls.js`.
- DataLens applies dynamic selector param changes only on subsequent selector updates, not on the first dashboard render.

Hydrate the remote baseline first when this folder maps to an existing widget entry.
