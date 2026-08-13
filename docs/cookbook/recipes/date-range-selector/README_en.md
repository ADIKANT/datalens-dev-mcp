# Date range selector

[Русский](README.md) · **English**

[← Cookbook](../../README_en.md) · [Web](https://adikant.github.io/datalens-dev-mcp/recipes/date-range-selector/?lang=en)

![Date range selector](preview_en.svg)

A date range with two explicit parameters.

## When to use it

A shared dashboard period through dateFrom and dateTo.

## Specific behavior

An incomplete manual range does not change confirmed Params.

## Sources contract

No external source is required.

## What to change

1. Replace Meta and Sources only; keep aliases stable.
2. Use the CUSTOMIZE block for optional labels, palette, units, and formatting.

## Files

- [`meta.json`](code/en/meta.json)
- [`params.js`](code/en/params.js)
- [`sources.js`](code/en/sources.js)
- [`controls.js`](code/en/controls.js)
- [`schema.json`](code/en/schema.json)
- [`example_input.json`](code/en/example_input.json)
