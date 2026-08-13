# Area chart

[Русский](README.md) · **English**

[← Cookbook](../../README_en.md) · [Web](https://adikant.github.io/datalens-dev-mcp/recipes/area-chart/?lang=en)

![Area chart](preview_en.svg)

A line filled to the zero axis to emphasize volume.

## When to use it

Volume over time when the filled area aids reading.

## Specific behavior

Values are not accumulated: Prepare renders the supplied series as-is.

## Sources contract

| Alias | Purpose | Type / format | Null behavior | Example |
| --- | --- | --- | --- | --- |
| `bucket` | Start of the displayed time interval after grouping, such as a day, week, or month. Values must sort chronologically. | `string` / ISO date or interval key | The row is discarded | `"2026-01-01"` |
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
