# Validation Evidence Model

Validation evidence reports state exactly what MCP verified and what remains
outside the current runtime surface.

`dl_build_validation_evidence_report` collects:

- `static_js_syntax`: JS template syntax gate coverage;
- `static_sql_lint`: generated Source/Editor SQL lint;
- `dashboard_payload_preflight`: dashboard payload id/layout/name checks;
- `safe_apply_plan`: approval and planned action summary;
- `dry_run_summary`: parsed project live workflow summary JSON;
- `saved_readback`: saved-branch readback evidence when present;
- `published_readback`: published-branch readback evidence when present;
- `editor_object_readback`: Editor object readback summary;
- `dashboard_layout_readback`: dashboard layout/readback summary;
- `runtime_publish_gate`: changed-tab browser/runtime verification result,
  including runtime error markers, visible changed objects, selector status,
  and proof artifacts;
- `source_availability_matrix`: per-source environment availability with
  `NO TABLE`, `NO DATA`, `ERROR`, and `OK` semantics kept distinct;
- `direct_sql_execution`: DataLens API query execution status;
- `engine_probe`: recorded read-only schema/stage probe status, or
  `BLOCKED_ENGINE_PROBE` when no probe artifact exists;
- `proof_levels`: exact proof classes present in the report. Allowed values are
  `source_static`, `installed_static`, `live_read_only_api`, `save_readback`,
  `publish_readback`, `browser_rendered`, and `controlled_live_write`;
- `ok_proof_context`: proof context for the report-level `ok` field;
- `confidence_level`: `blocked`, `medium_static_only`,
  `medium_static_with_readback`, or method-specific status;
- `remaining_manual_checks`: live-only checks Codex must not claim as done.

When the curated DataLens API catalog has no validated query-execution method,
the report returns:

```json
{
  "direct_sql_execution": {
    "status": "blocked_runtime_sql_execution",
    "checked_catalog": "config/datalens_api_methods.json",
    "recommended_fallback": [
      "static SQL lint",
      "generated query inspection",
      "save/publish acceptance",
      "published object readback",
      "optional manual UI smoke"
    ]
  }
}
```

This is not a failure by itself. The report fails when static SQL lint,
dashboard preflight, or the standard validation report has blocking errors.

When engine probes are not recorded, the report also returns:

```json
{
  "engine_probe": {
    "status": "BLOCKED_ENGINE_PROBE",
    "next_steps": [
      "Use dl_build_data_evidence_probe_plan to prepare bounded probes",
      "Run probes through an approved read-only metadata/data evidence provider",
      "Record sanitized results with dl_record_data_evidence"
    ]
  }
}
```

Do not claim runtime SQL success from `source_static`, DataLens object
readback, or a blocked engine probe alone. Do not state a generic `ok` without
`proof_level`, `proof_levels`, or `ok_proof_context`.

API readback, `validateDataset`, and schema-level checks do not prove a changed
published chart renders in the browser. When a publish workflow changes tabs or
runtime objects, final delivery must include a passed `runtime_publish_gate`.
If browser/runtime verification is blocked by auth or tooling, the correct
handoff status is `runtime_not_verified`.
