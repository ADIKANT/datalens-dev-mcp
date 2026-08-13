# Bullet: actual and target

[Русский](README.md) · **English**

[← Cookbook](../../README_en.md) · [Web](https://adikant.github.io/datalens-dev-mcp/recipes/bullet-actual-target/?lang=en)

![Bullet: actual and target](preview_en.svg)

An actual value with a separate target marker.

## When to use it

Compact comparison of several items against individual targets.

## Specific behavior

target is a marker; value is a bar.

## Sources contract

| Alias | Purpose | Type / format | Null behavior | Example |
| --- | --- | --- | --- | --- |
| `label` | Displayed category | `string` / display label | The row is discarded | `"Category A"` |
| `group` | Group, series, or second matrix coordinate | `string` / series label | A shared group is used | `"Current period"` |
| `value` | Numeric mark value | `number` / finite number | Line gap or omitted mark | `42` |
| `target` | Target marker value | `number` / finite number | The row is not shown | `50` |

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
