# MCP Tool Selection Policy

Normal Codex work uses the standard tool surface from `tools/list`. Do not ask
the operator to pick profiles. Hidden compatibility tools remain for tests and
explicit internal flows only, and require `DATALENS_MCP_TEST_ONLY_REGISTRY=1`
plus `DATALENS_MCP_ALLOW_HIDDEN_TOOL_CALLS=1`.

Use this order for normal Codex work:

1. `dl_runtime_status` and `dl_auth_probe` for live readiness.
2. Call Project Memory Bank `memory_context`, then pass the returned
   `project_context_ref.v1` to project-aware DataLens operations.
3. `dl_get_workbook_entries`, `dl_read_object`, `dl_snapshot_dashboard`, and
   `dl_get_entries_relations` for compact evidence.
4. `dl_reference` only for bounded rules, recipes, formulas, runtime contracts,
   chart selection, negative requirements, delivery intent, API contracts,
   current-docs deltas, and tool selection.
5. `dl_diagnose` for bounded SQL, grain, graph, performance, and optimization
   diagnostics with artifact-backed detail.
6. `dl_validate_editor_runtime_contract`, `dl_validate_object`, and
   `dl_validate_project` before payload planning.
7. `dl_build_payload_plan`, `dl_create_safe_apply_plan`, and
   `dl_create_publish_from_saved_plan` for guarded write planning.
8. `dl_execute_safe_apply` only after explicit approval and enabled writes.
9. `dl_readback_and_report` for saved and published proof.

Stage-specific reference modes:

| Stage | Use `dl_reference(mode=...)` | Next standard tools |
| --- | --- | --- |
| Chart family and route choice | `chart_selection` | `dl_validate_project`, `dl_build_payload_plan` |
| Renderer/runtime checks | `renderer_contract` | `dl_validate_editor_runtime_contract`, `dl_validate_project` |
| User removals and exclusions | `negative_requirements` | `dl_validate_project`, `dl_build_payload_plan` |
| Save/publish intent | `delivery_intent` | `dl_create_safe_apply_plan`, `dl_execute_safe_apply`, `dl_readback_and_report` |
| API method ownership | `api_contract` | `dl_list_api_methods`, `dl_get_api_method_schema`, `dl_read_object`, `dl_plan_object_update` |
| Current official docs deltas | `current_docs_delta` | `dl_reference(mode='api_contract')`, `dl_validate_project` |
| Tool navigation | `tool_selection` | `dl_runtime_status`, `dl_auth_probe`, `dl_reference` |

`api_contract` and `current_docs_delta` point to compact current docs/API
reconciliation artifacts: `config/datalens_api_operation_policy.json`,
`docs/datalens/api_contract_coverage.md`,
`config/datalens_docs_feature_policy.json`, and
`docs/datalens/current_docs_reconciliation.md`. They do not inline long
official documentation pages.

Do not use raw RPC for normal workflows. `dl_rpc_readonly` and `dl_rpc_expert`
are not on the standard surface. Use API schema lookup and object lifecycle
planning instead.

Chart authoring is Wizard-first. Standard native charts use `wizard_native`;
`wizard_map_native` is a `geolayer` compatibility alias. Editor routes are
selected by explicit request, dedicated Markdown/control/table semantics, or a
registered capability gap. QL uses the existing generic lifecycle tools only
when the user directly requests `ql_explicit`; it is never a default or
fallback, and QL delete remains closed.
