# Sankey

[Русский](README.md) · **English**

[← Cookbook](../../README_en.md) · [Web](https://adikant.github.io/datalens-dev-mcp/recipes/sankey/?lang=en)

![Sankey](preview_en.svg)

Flows between nodes with link width proportional to volume.

## When to use it

Transition routes between multiple states.

## Specific behavior

Geometry contains separate nodes and links; cyclic links are unsupported.

## Sources contract

| Alias | Purpose | Type / format | Null behavior | Example |
| --- | --- | --- | --- | --- |
| `source` | Source flow node | `string` / node label | The flow is invalid | `"New"` |
| `target` | Target flow node | `string` / node label | The flow is invalid | `"In progress"` |
| `value` | Numeric mark value | `number` / finite number | Line gap or omitted mark | `42` |

## What to change

1. Replace Meta and Sources only; keep aliases stable.
2. Use the CUSTOMIZE block for optional labels, palette, units, and formatting.

## Files

- [`meta.json`](code/en/meta.json)
- [`params.js`](code/en/params.js)
- [`sources.js`](code/en/sources.js)
- [`controls.js`](code/en/controls.js)
- [`prepare.js`](code/en/prepare.js)
- [`schema.json`](code/en/schema.json)
- [`example_input.json`](code/en/example_input.json)
