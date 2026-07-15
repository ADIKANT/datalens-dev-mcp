# Golden Runtime Gallery

The MCP-supported chart creation routes are closed and represented by generated golden contracts.
The gallery is a regression fixture and runtime-proof ledger, not a reusable business dashboard.

## Route Inventory

| Class | Routes |
| --- | --- |
| supported | `wizard_native`, `editor_advanced`, `editor_table`, `editor_markdown`, `editor_js_control`, `ql_explicit` |
| reference_only | `grouped_sticky_table_exception`, `unknown_wizard_visualization` |
| unsupported | `regular_editor_chart`, `gravity_ui_charts` |
| banned | `d3_node`, `ql_delete`, `automatic_ql_selection`, `runtime_route_fallback`, `guessed_id_write`, `blind_write_or_publish`, `production_workbook_mutation` |

## Contract Summary

- Supported family contracts: `39`
- Families by route: `{"editor_advanced": 9, "editor_js_control": 6, "editor_markdown": 6, "ql_explicit": 1, "wizard_native": 17}`
- Saved readback available: `0`
- Published readback available: `0`
- Browser render proof available: `0`
- Browser render proof unavailable: `39`

Saved readback, published readback, and browser screenshots remain `unavailable` in the checked-in
static contracts because no disposable workbook, guarded write approval, rendered URL, or authenticated
browser evidence was supplied for this static release snapshot.

## Contract Files

- `config/golden_runtime_gallery_inventory.json`
- `config/golden_runtime_gallery_contracts.json`
- `examples/golden_runtime_gallery/golden_runtime_gallery_contracts.json`
