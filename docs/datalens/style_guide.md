# DataLens Style Guide

`config/datalens_style_guide.json` is the editable source of truth for MCP
generated DataLens visuals. Chart code should follow this flow:

```text
style guide -> template params -> generated chart code
```

Prompts and routing rules choose a chart family. The template registry loads the
family template. Template params and shared helpers then pass resolved theme
tokens into `prepare.js`/`controls.js` code. Generated chart code must not invent
ad hoc colors.

## Theme Tokens

Each theme defines the same token names:

- dashboard background
- card background
- text primary, secondary, and muted
- border and grid line
- tooltip background and text
- accent, warning, error, and success
- neutral, categorical, and sequential palettes
- table header and row background
- selector label text

The light and dark themes use DataLens/Gravity CSS variables where DataLens can
resolve them at runtime. Fallback hex values are present only for standalone
rendering, tests, and exports outside the DataLens shell.

## Template Rules

- Advanced Editor templates import `HOUSE_STYLE` from
  `templates/datalens/advanced_editor/_shared/style_tokens.js`.
- Render callbacks receive the active style object through `Editor.wrapFn`
  `args`; callbacks do not close over helper imports.
- Table and selector routes use route-native style fields instead of wrapping
  table/selector UI in Advanced Editor HTML.
- Category palettes are visual categories only. Warning, error, and success
  states use semantic tokens.
- If the DataLens runtime does not expose the active theme state, templates use
  `light` as the deterministic default and preserve `var(--g-color-*)` CSS
  variables so the host theme can still resolve them.

## DAGS Checker Table Pattern

The DAGS Checker table code is the table-style reference pattern. Table cells
and headers must use DataLens/Gravity CSS variables such as:

- `var(--g-color-text-primary, inherit)`
- `var(--g-color-text-secondary, inherit)`
- `var(--g-color-base-background, transparent)`
- `var(--g-color-base-neutral-light, transparent)`
- `var(--g-color-text-danger, inherit)`
- `var(--g-color-base-danger-light, rgba(255, 77, 79, 0.16))`
- `var(--g-color-text-warning, inherit)`
- `var(--g-color-base-warning-light, rgba(255, 190, 92, 0.18))`
- `var(--g-color-text-positive, inherit)`
- `var(--g-color-base-positive-light, rgba(48, 191, 113, 0.16))`

Light-only fills such as `#F7F9FC`, `#FDECEC`, `#ECF7EF`, and `#FFF7E0` are not
allowed in generated table templates because they break dark theme rendering.

## Editing Process

1. Update `config/datalens_style_guide.json`.
2. Mirror changed runtime tokens in
   `templates/datalens/advanced_editor/_shared/style_tokens.js` if generated JS
   needs the new token.
3. Update template `params.json` or `prepare.js` only when the token changes how
   chart code renders.
4. Run the style guide unit test and JavaScript syntax checks.
