# One-Prompt Workflow

[Русский Flow](usage-flow.md) · [English flow](usage-flow_en.md) · [Public tools](tools_en.md)

An MCP client may receive a broad request such as:

```text
разработай мне дашборд на основе требований и вот этих данных
```

The agent should resolve it through the standard public surface:

1. Call `dl_runtime_status` and `dl_auth_probe`.
2. When a live target exists, read workbook inventory, create a fresh dashboard
   snapshot, and read exact objects and relations.
3. Use `dl_reference` for bounded route/API guidance and `dl_diagnose` for
   supplied SQL, grain, or performance evidence.
4. Build generic create/update plans with `dl_plan_object_create` or
   `dl_plan_object_update`; use the guarded dataset or dashboard-tab planner
   only for those specialized changes.
5. Run `dl_validate_object`, optional Editor runtime validation, and
   `dl_validate_project`.
6. Build `dl_build_payload_plan` and an unapproved
   `dl_create_safe_apply_plan`.
7. Stay read-only or plan-only unless the requested delivery intent, tool
   approval, and runtime gates allow guarded execution.
8. After any save, require saved readback. Publish only through
   `dl_create_publish_from_saved_plan`, followed by published readback and
   runtime/browser QA for visible changes.

The prompt is not permission to guess object IDs, choose QL automatically,
call hidden compatibility tools, or bypass write/save/publish gates.
