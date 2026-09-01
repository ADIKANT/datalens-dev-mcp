# Wizard Chart Templates

Source trace: OpenAPI Wizard methods, `config/route_selection_policy.json`,
`templates/datalens/wizard/wizard_template_registry.json`,
`templates/datalens/wizard/canonical_templates.json`, and the Wizard schemas.

All 17 observed native IDs have anonymized canonical templates: `metric`,
`flatTable`, `pivotTable`, `line`, `area`, `area100p`, `column`, `column100p`,
`bar`, `bar100p`, `combined-chart`, `pie`, `donut`, `scatter`, `treemap`,
`funnel`, and `geolayer`. The registry records semantic families, required/optional roles,
template provenance, seed policy, and live verification state.

## Builder Contract

Input contains exactly one location form (`key` or `workbookId + name`), a
dataset binding, semantic field bindings, visualization ID, options, and an
optional saved seed. Output contains source kind, sanitized seed binding/hash,
compiled request payload, and a validation report.

A template may be compiled offline without dataset readback evidence, but that
plan is not live-execution-ready. A canonical fixture is never sufficient for
live create by itself: live execution additionally requires a revision-bound
saved seed of the same visualization and a matching runtime-shape hash. Wizard
create requires fresh saved
`dataset_readbacks`; the compiler keeps only the bound dataset identity and
referenced field GUID/type pairs, checks that the evidence belongs to the
payload dataset, and rejects role/type mismatches before payload or safe-apply
planning. Create planning also requires workbook entries reconciliation and a
deterministic object-reuse decision.

Immediately before create, safe apply refreshes the workbook inventory through
bounded pagination, merges entries deterministically by identity, and repeats
the reuse check. Cursor cycles, incomplete pages, capacity limits, conflicting
duplicate identities, or a compatible object found on any page block the write.

A seed is accepted only from the saved branch with a fresh revision and the
same visualization ID. Create sanitization removes entry, revision, and
location identities while preserving unknown `data` fields, then rebinds the
dataset and field GUIDs. The compiler preserves the saved seed's nested or flat
`datasetsPartialFields` container and unknown field metadata. Missing seed uses
the canonical template for offline planning only and produces
`live_execution_ready=false`. Canonical fixtures are offline evidence and have
`live_verification=false`.

For a public create manifest, every `wizard_chart` object therefore declares a
project-relative `wizard_seed_path`. The referenced JSON must be a fresh saved
readback with a revision and the same visualization. A missing, mismatched, or
shape-incompatible seed blocks before Safe Apply and before any write.

Funnel uses the native `funnel` ID. Its current payload contract places the
category dimension and one or more measures in the required `measures`
placeholder; alternatively, multiple measures generate the Measure Names
category. The compiler therefore requires at least two bound items. The
visualization permits color, labels, filters, and sorting; exact optional
presentation fields are preserved from a fresh saved seed. Bubble requires
`size`; geolayer requires validated geo evidence. Unknown
visualization IDs block create. Update can preserve an unknown ID only from
fresh saved readback. No identifier token is guessed.

JavaScript is not an error fallback. It is selected before transport only for
an explicit request or a capability gap registered in the route policy.
