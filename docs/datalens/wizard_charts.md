# Wizard Charts

`wizard_native` is the primary route for new standard DataLens charts. It uses
the official Wizard read/create/update lifecycle and one of the 16 canonical
visualization IDs documented in `docs/datalens/wizard_chart_templates.md`.
`wizard_map_native` remains accepted as an alias for `geolayer`.

Route selection happens before transport. Standard semantics select Wizard;
JavaScript is selected only by explicit request or registered capability gap.
Existing objects retain the technology and visualization ID from fresh saved
readback unless the user explicitly asks for migration.

Configuration and payload-plan schemas are
`schemas/wizard-chart-config.schema.json` and
`schemas/wizard-payload-plan.schema.json`. The compiler lives in
`src/datalens_dev_mcp/pipeline/wizard_templates.py`, prefers a fresh same-ID
saved seed, sanitizes create identities, rebinds dataset/field GUIDs, and falls
back to the committed canonical template. It never claims live verification
for an offline template.

Maps additionally require geo evidence; bubble additionally requires a size
role. Stale, published-branch, mismatched, or identity-bearing create seeds are
blocked or sanitized according to the validation report. Unknown IDs cannot be
created and can only be preserved on update from fresh saved readback.
