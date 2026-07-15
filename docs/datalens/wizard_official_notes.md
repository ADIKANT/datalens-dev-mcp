# Wizard Official Notes

Sources: the official DataLens API and Wizard documentation, the compiled
request schemas, and `docs/route-policy.md`.

## API Evidence

- Official API exposes experimental Wizard chart read/create/update methods. MCP records this as `PLAN_ONLY_SUPPORTED` for create/update and `EXECUTABLE_TOOL_SUPPORTED` for read. Source trace: `config/datalens_api_methods.json`, `Wizard` tag.
- Wizard payload structure is official evidence for native standard chart planning across the 16 observed visualization IDs. Source trace: `docs/route-policy.md` and the canonical template registry.
- Public examples use synthetic identifiers and contain no exported live
  payloads.

## Native Map Contract

- Route id: `wizard_native`; `wizard_map_native` is a compatibility alias for `geolayer`.
- Required inputs: workbook context, dataset reference, map question, geo field/evidence (`geopoint`, `geopolygon`, or lat/lon), measures, grouping dimension where needed, filters, selector bindings, tooltip fields, color role, and native dashboard/widget title/hint metadata.
- Missing geo evidence returns a targeted question instead of inventing a map payload.
- If a user explicitly requests JavaScript map rendering, return a blocked-route diagnostic: Advanced Editor map creation is closed by route policy; native Wizard map is the supported lane.

## Dashboard Integration

- Wizard widgets must be represented in dashboard object relations with selector targets and source dataset/connection dependencies.
- Titles and hints stay in dashboard/widget metadata (`hideTitle=false`, `enableHint=true`) unless a source requirement explicitly asks for an internal chart label.
- Native maps should inherit dashboard theme tokens and filter behavior; avoid duplicating controls inside a map body.

## Native Boundary

- Standard line, area, bar/column, table/pivot, KPI, combined, pie/donut, scatter/bubble, treemap, and map charts are Wizard-first.
- Unknown visualization IDs remain create-blocked and may be updated only from fresh saved readback. JavaScript is used only for a registered capability gap, never after a failed Wizard attempt.
