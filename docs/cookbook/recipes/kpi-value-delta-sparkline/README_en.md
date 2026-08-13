# KPI: delta and trend

[Русский](README.md) · **English**

[← Cookbook](../../README_en.md) · [Web](https://adikant.github.io/datalens-dev-mcp/recipes/kpi-value-delta-sparkline/?lang=en)

![KPI: delta and trend](preview_en.svg)

A KPI with a value, explicit comparison, and sparkline.

## When to use it

A primary metric that needs level, change, and trend.

## Specific behavior

Tooltip shows time-point values and comparison context.

## Sources contract

| Alias | Purpose | Type / format | Null behavior | Example |
| --- | --- | --- | --- | --- |
| `current_value` | Current metric value | `number` / finite number | Shows the empty state | `128` |
| `comparator_value` | Explicit comparison value | `number` / finite number | Delta is not calculated | `120` |
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
