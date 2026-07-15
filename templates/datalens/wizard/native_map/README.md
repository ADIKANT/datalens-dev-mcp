# Wizard Native Map Template

Source trace: official Wizard API/docs extraction, `schemas/wizard-chart-config.schema.json`, `config/datalens_chart_param_matrix.json`, and demo-workbook harvest plan.

- Route: `wizard_native` with `visualization_id=geolayer`;
  `wizard_map_native` is accepted as a compatibility alias.
- Required: dataset reference, geo evidence, dimensions/measures, filters, style/theme tokens, labels, legend, tooltip settings, selector bindings, and native metadata.
- Output: schema-validated plan-only `createWizardChart` contract with `execute_now=false`.
- Prefer a fresh same-ID saved seed; otherwise use the anonymized canonical
  geolayer template. Offline fixtures do not claim live verification.
- Other standard native IDs are defined in
  `templates/datalens/wizard/canonical_templates.json`.
