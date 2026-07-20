# Advanced Editor Template Guide

Sources: the official DataLens Editor documentation,
`docs/datalens/advanced_editor_contract.md`, the parameter matrix, and the
project-authored templates.

- `prepare.js` normalizes loaded rows, creates a serializable model, and exports `render: Editor.wrapFn({args, fn})`.
- Render functions receive every dependency through `args` and return `Editor.generateHtml(...)`.
- Top-level widget title and hint are native dashboard metadata; chart bodies do not render duplicated title rows or hint icons.
- Comments should explain source normalization, data shaping, formatting, style tokens, interactivity and empty state only where the code would otherwise be ambiguous.

## Required Template Comment Blocks

Every Advanced Editor `prepare.js` must keep a compact contract header covering:

- source/data contract;
- params/config;
- prepare/model normalization;
- render lifecycle;
- layout/scales;
- labels/tooltips;
- theme tokens;
- interactions;
- extension points.

These labels are intentionally deterministic so reviews and tests can detect generated or hand-written templates that skipped the contract.

## Parameterization

- `schema.json` and `example_input.json` define accepted input shape for each template archetype.
- `templates/datalens/standard_chart_templates.json` maps every supported Advanced Editor family to an archetype.
- `config/datalens_chart_param_matrix.json` adds family-level required parameters, optional parameters, sorting, label/axis/gridline behavior, color strategy, value formatting, interaction expectations, ask-user triggers, and fallback family.
- `load_standard_template_bundle` attaches the matrix `parameter_spec` to generated bundles.

## Visual Rules

- No 3D, shadows, ornamental backgrounds, decorative gradients, or chartjunk.
- Use shared `HOUSE_STYLE` tokens and accessible semantic colors.
- Bars use an explicit zero baseline and signed numeric domains; time charts
  show grain; numeric relationship/distribution charts name axes and units.
- Part-to-whole, flow, stacked-100, and funnel renderers fail closed instead
  of drawing invalid geometry for negative, missing, over-limit, or
  non-monotonic inputs.
- Labels/tooltips should reduce lookup and explain metric/source context without duplicating dashboard metadata.
- Every renderer derives mounted dimensions from `options.width` and
  `options.height`; executable probes cover 236, 360, 530, 560, 700, and 900
  pixel widths at three independent heights for all 25 registered Advanced
  Editor families. The 450-probe sweep rejects fixed minimums and invalid
  geometry that force viewport overflow.
- Missing time-series observations remain null points that split line
  segments. Trailing future null-only buckets are omitted instead of being
  plotted as observed zeroes.
