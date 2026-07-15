# API Tool Mapping

Source trace: `config/datalens_api_methods.json`, `schemas/datalens-api/support-policy-overlay.json`, MCP object lifecycle tools, `dl_rpc_readonly`, and safe apply policy.

| MCP surface | Official method(s) | Support status | Notes |
| --- | --- | --- | --- |
| `dl_rpc_readonly` | all curated `readonly` methods, including QL reads | `EXECUTABLE_TOOL_SUPPORTED` | Read-only RPC only; no writes. |
| `dl_read_object` / object readers | `getDashboard`, `getEditorChart`, `getWizardChart`, `getDataset`, `getConnection` | `EXECUTABLE_TOOL_SUPPORTED` | Saved/published branch reads where applicable. |
| Dashboard lifecycle planners | `createDashboard`, `updateDashboard` | `PLAN_ONLY_SUPPORTED` | Safe-apply plan; save by default. |
| Advanced Editor planners | `createEditorChart`, `updateEditorChart` | `PLAN_ONLY_SUPPORTED` | JavaScript is selected explicitly or for a registered Wizard capability gap. |
| Wizard native planners | `createWizardChart`, `updateWizardChart` | `PLAN_ONLY_SUPPORTED` | Wizard-first standard visualizations use canonical templates or a matching fresh saved seed. |
| Dataset/connector planners | `createDataset`, `updateDataset`, `createConnection`, `updateConnection`, `validateDataset` | `PLAN_ONLY_SUPPORTED` / `EXECUTABLE_TOOL_SUPPORTED` | Create/update are plans; validation/read are read-only. |
| QL methods | `getQLChart`, `createQLChart`, `updateQLChart` | `EXECUTABLE_TOOL_SUPPORTED` / `PLAN_ONLY_SUPPORTED` | QL create/update requires `ql_explicit` and direct-user-request provenance. |
| QL delete | `deleteQLChart` | `READ_ONLY_REFERENCE` | Delete remains policy-blocked. |
| Delete/move/permission/license mutation | delete/move/permission/license RPCs | `READ_ONLY_REFERENCE` / policy blocked | Documented for awareness; not an operator route. |

