# Chart Template Playbook

This project-authored playbook is backed by
`config/datalens_chart_param_matrix.json`, the route policy, the official
DataLens visualization reference, and the registered templates.

## Template Selection

1. Normalize the requested chart family with `chart_taxonomy.resolve_chart_family`.
2. Load the family spec from `chart_param_matrix.get_chart_param_spec`.
3. Use the matrix route as the supported route. A caller-provided route must match the matrix route.
4. For `wizard_native`, compile the mapped canonical Wizard visualization and
   prefer a fresh same-ID saved seed.
5. Load `templates/datalens/standard_chart_templates.json` only for a dedicated
   Editor route or registered JavaScript capability gap. Geolayer additionally
   requires geographic evidence.

## Parameterization Checklist

- Validate required parameters before generating tabs or payloads.
- Populate optional parameters only when the requirement or data profile provides evidence.
- Apply default sorting from the matrix unless the business order is declared.
- Apply label, axis, gridline, color, formatting, and interaction rules from the matrix.
- Return the matrix `ask_user_when` reason instead of guessing required evidence.
- Fall back to the matrix fallback family when cardinality, evidence, or readability constraints fail.

## Route Guardrails

- Executable creation routes are `wizard_native`, the four registered Editor
  routes, and direct-request-only `ql_explicit`.
- Wizard is the default for standard chart semantics; `wizard_map_native` is a
  `geolayer` compatibility alias.
- JavaScript and QL are selected before transport, never as runtime fallbacks.
- Unsupported chart requests are normalized to approved alternatives or held for manual review.
- Chart titles and hints belong to native DataLens metadata unless the user explicitly asks for in-body text.
