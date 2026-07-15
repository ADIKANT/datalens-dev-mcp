# Advanced Editor Methods

Sources: <https://yandex.cloud/ru/docs/datalens/charts/editor/>, the packaged
official-documentation registries, and the project runtime validators.

## Allowed `Editor` Methods

The supported methods are:

| Method | MCP use |
|---|---|
| `Editor.generateHtml(arg)` | Return sanitized HTML from wrapped Advanced renderers. |
| `Editor.getActionParams()` | Read cross-filter/action state when explicitly needed. |
| `Editor.getCurrentPage()` | Read pagination context. |
| `Editor.getId(arg)` | Resolve aliases from `meta.json` links. |
| `Editor.getLang()` | Read user language. |
| `Editor.getLoadedData()` | Read source results on `prepare.js` or controls tabs. |
| `Editor.getParam(name)` | Read one normalized parameter as an array. |
| `Editor.getParams()` | Read all normalized parameters. |
| `Editor.getSortParams()` | Read sort state. |
| `Editor.getWidgetConfig()` | Read widget config when the route supports it. |
| `Editor.resolveInterval(arg)` | Resolve relative interval values. |
| `Editor.resolveOperation(args)` | Resolve operation expressions. |
| `Editor.resolveRelative(arg)` | Resolve relative date/period values. |
| `Editor.setChartsInsights(args)` | Set insights when explicitly designed. |
| `Editor.updateActionParams()` | Update cross-filter/action params only for explicit interactions. |
| `Editor.updateParams(params)` | Last-resort parameter update; prefer controls. |
| `Editor.wrapFn(conf)` | Wrap render, tooltip, and event callbacks. |

## Runtime Model

- Editor tabs run in the server-side DataLens execution context; `wrapFn`
  callbacks run later in a client or sandbox context.
- `Meta.links`, `entry.links`, and `Editor.getId(alias)` must stay consistent so
  relation graphs, workbook copy/export, and sources can resolve datasets and
  connections.
- Treat `Params` values as normalized arrays. Reserved DataLens parameter names
  are not template parameter names.
- `Sources` loads bounded data and `Prepare` reduces it before render.

## Performance Budget

- Source data should be filtered before charts; avoid sending large raw arrays into `wrapFn.args`.
- `Prepare` must do aggregation/model normalization; render callbacks must only lay out the precomputed model.
- Advanced HTML/SVG output should be compact and theme-tokenized.
- If row count, source size, or render complexity cannot be bounded, ask one targeted question or return a missing-capability diagnostic.

## Unavailable Or Non-Generated Methods

Do not generate calls to methods outside the allowed list. In particular, MCP
templates must not call:

- `Editor.getData()`
- `Editor.fetch()`
- `Editor.render()`
- `Editor.create*()`
- `Editor.update*()` methods other than `updateParams` and `updateActionParams`
- `Editor.save*()`
- `Editor.publish*()`
- browser globals such as `window`, `document`, or direct DOM mutation APIs

If a source example needs a method not in the allowed list, stop template
generation and create a compact missing-capability diagnostic instead.

## Templates

The public template set under `templates/datalens/` uses synthetic inputs and
is validated by the JavaScript and route-policy checks.
