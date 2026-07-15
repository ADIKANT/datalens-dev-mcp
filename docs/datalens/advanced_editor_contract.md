# Advanced Editor contract

This contract prevents historical `render` and `wrapFn` failures in MCP-native
Advanced Editor templates.

Sources: the official DataLens Editor documentation, the method inventory in
`docs/datalens/advanced_editor_methods.md`, and the project runtime validators.

## Render Lifecycle

1. `sources.js` defines data bindings and query output names.
2. Top-level `prepare.js` reads loaded data and params, normalizes rows, performs
   aggregation, builds tooltip rows, and creates a compact serializable `model`.
3. `module.exports` exposes `render: Editor.wrapFn({args, fn})`.
4. The wrapped `fn` receives chart options as its first argument. Template
   convention is:

```js
const model = {title: 'Chart', rows, style: HOUSE_STYLE};

module.exports = {
  render: Editor.wrapFn({
    args: [model],
    fn: function(options, data) {
      return Editor.generateHtml('<div>...</div>');
    },
  }),
};
```

The canonical shape is `render: Editor.wrapFn({`, `args: [model]`,
`fn: function(options, data)`, and `return Editor.generateHtml(...)`.

## Correct `wrapFn` Usage

Wrap only callbacks that DataLens executes later:

- `render`
- `tooltip.renderer`
- event callbacks such as click handlers, when explicitly needed

The callback must be self-contained. Anything it uses must be:

- defined inside the callback;
- a standard JavaScript global such as `Math`, `Number`, or `String`; or
- passed through `args` as serializable data.

Imported helpers, top-level helper functions, and top-level constants are not
safe inside the wrapped callback unless their values are passed through `args`.

## What must not be wrapped

These parts must not be wrapped:

- source/data binding in `sources.js`;
- top-level prepare-time data normalization;
- schema/config objects;
- table `prepare.js` for `table_node`;
- Markdown `prepare.js`;
- control definitions unless a specific control callback is required.

## Correct Return Behavior

- Advanced `render` callbacks return `Editor.generateHtml(...)`.
- Do not export `render: Editor.generateHtml(...)` directly.
- Do not return raw DOM nodes unless immediately wrapped in
  `Editor.generateHtml(...)`.
- `table_node` returns `{head, rows}` and must not use `Editor.generateHtml`.
- Markdown returns `{markdown}` and must not use `Editor.wrapFn`.

## Data Access Pattern

- Read data with `Editor.getLoadedData()` at prepare time.
- Normalize event-stream rows from metadata plus row events before array
  operations.
- Use `Editor.getParam(name)` or `Editor.getParams()` for normalized params.
- Do not mutate the params object. `Editor.updateParams(params)` is last-resort
  interaction logic and should not appear in standard chart templates.
- Resolve dataset and connection aliases with `Editor.getId(alias)` only when `Meta.links` declares the alias.
- Keep source limits and row reduction in `sources.js`/`prepare.js`; do not transfer unnecessary raw rows into `wrapFn.args`.

## Native Titles And Hints

- Dashboard/widget metadata is the standard surface for chart titles and hints.
- Advanced chart bodies must not draw dashboard-level titles unless a source requirement explicitly asks for an in-chart annotation.
- Template `README.md`, `meta.json`, and example inputs should expose title/hint metadata separately from rendered chart body content.

## Historical Mistakes And Prevention

| Mistake | Prevention |
|---|---|
| `render` assigned to `Editor.generateHtml(...)` instead of `Editor.wrapFn`. | Validator rejects direct render exports. |
| `Editor.wrapFn` called with shorthand callback instead of `{args, fn}`. | Validator requires object-form wrapFn. |
| Wrapped callback reads imported helpers or top-level functions. | Templates pass serializable `style`/model data and define render helpers inside `fn`. |
| Business metrics recalculated inside `fn`. | Templates normalize and aggregate before `args: [model]`. |
| Unsupported `Editor` methods guessed by model. | Validator scans `Editor.<method>(...)` against the allowed list. |
| Table/Markdown routed through Advanced render because it was convenient. | Route contract keeps `table_node`, Markdown, selectors, and Advanced separate. |

## Template Constraints

- Use `templates/datalens/standard_chart_templates.json`.
- Prefer an existing registered template over improvised JS.
- Keep `sources.js`, params, prepare/model, render/layout, style tokens, and
  helpers separate.
- Put comments at the `Source/data contract`, `Params/config`, `Prepare/model normalization`, `Render/layout`, `Labels/tooltips`, `Theme tokens`, `Interactions`, and `Safe render contract` boundaries.
- Do not hardcode source object IDs, workbook IDs, dataset IDs, or local paths.
- Use only methods listed in `docs/datalens/advanced_editor_methods.md`.

## Minimal Validation Checks

The validator intentionally catches only meaningful Advanced failures:

- unavailable `Editor` method calls;
- missing `render: Editor.wrapFn({ ... })`;
- missing `args`;
- missing `fn: function(...)`;
- direct `render: Editor.generateHtml(...)`;
- wrapped render callback that does not return `Editor.generateHtml(...)`.

Validation is not a substitute for the templates; templates must already follow
the contract by construction.

## fallback behavior

If a requested chart cannot be generated safely:

1. Resolve the family through the supported taxonomy.
2. Use the registered standard template if available.
3. If no safe template exists, generate a simple governed Advanced fallback with
   the canonical `args: [model]` / `fn: function(options, data)` shape.
4. If the requested route or method is unsupported, return a compact diagnostic
   naming the missing input/capability and ask one specific question.
