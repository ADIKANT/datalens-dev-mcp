# Wizard And JavaScript Technology Preservation

Technology changes start with fresh saved readback and an explicit migration
request. They are never a default update or a fallback after a transport error.

- Existing Wizard charts preserve their visualization ID.
- New standard charts use `wizard_native`; maps use `geolayer` and require geo
  evidence.
- Custom visuals route to `editor_advanced` only by explicit request or a
  registered capability gap.
- Ordinary tables/pivots use Wizard; specialized grouped/pinned tables use
  `editor_table`.
- Text blocks use `editor_markdown`; controls use `editor_js_control`.
- Ambiguous migrations are `manual_review_required`.
