# KPI: value and trend

[Русский](README.md) · **English**

[← Cookbook](../../README_en.md) · [Web](https://adikant.github.io/datalens-dev-mcp/recipes/kpi-value-sparkline/?lang=en)

![KPI: value and trend](preview_en.svg)

A metric with a compact sparkline.

## When to use it

A current total where the recent trend shape matters.

## Specific behavior

The sparkline preserves null gaps without inventing values.

## Sources contract

| Alias | Purpose | Type / format | Null behavior | Example |
| --- | --- | --- | --- | --- |
| `current_value` | Current metric value | `number` / finite number | Shows the empty state | `128` |
| `sparkline` | Value sequence for the sparkline | `string` / JSON number array | The sparkline is hidden | `"[82,91,97,104,128]"` |

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
