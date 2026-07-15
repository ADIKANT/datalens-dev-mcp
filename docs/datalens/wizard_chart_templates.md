# Wizard Chart Templates

Source trace: OpenAPI Wizard methods, `config/route_selection_policy_v5.json`,
`templates/datalens/wizard/wizard_template_registry.json`,
`templates/datalens/wizard/canonical_templates.json`, and the Wizard schemas.

All 16 observed native IDs have anonymized canonical templates: `metric`,
`flatTable`, `pivotTable`, `line`, `area`, `area100p`, `column`, `column100p`,
`bar`, `bar100p`, `combined-chart`, `pie`, `donut`, `scatter`, `treemap`, and
`geolayer`. The registry records semantic families, required/optional roles,
template provenance, seed policy, and live verification state.

## Builder Contract

Input contains exactly one location form (`key` or `workbookId + name`), a
dataset binding, semantic field bindings, visualization ID, options, and an
optional saved seed. Output contains source kind, sanitized seed binding/hash,
compiled request payload, and a validation report.

A seed is accepted only from the saved branch with a fresh revision and the
same visualization ID. Create sanitization removes entry, revision, and
location identities while preserving unknown `data` fields, then rebinds the
dataset and field GUIDs. Missing seed uses the canonical template. Canonical
fixtures are offline evidence and have `live_verification=false`.

Bubble requires `size`; geolayer requires validated geo evidence. Unknown
visualization IDs block create. Update can preserve an unknown ID only from
fresh saved readback. No identifier token is guessed.

JavaScript is not an error fallback. It is selected before transport only for
an explicit request or a capability gap registered in the route policy.
