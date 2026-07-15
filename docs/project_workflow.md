# Project Workflow

[Русский Flow](usage-flow.md) · [English flow](usage-flow_en.md) · [Public tools](tools_en.md)

This guide covers downstream DataLens project directories through the standard
38-tool MCP surface. The selected `--project-root` is the only location where
the server may create project plans, validation artifacts, snapshots, and
deployment reports. It does not imply a live workbook or dashboard target.

Compatibility/test-only helpers may exist for regression coverage, but they
are absent from normal `tools/list` and are not part of this workflow.

## Standard object workflow

For a normal project without a custom executor:

1. Call `dl_runtime_status` and `dl_auth_probe`.
2. Read live evidence with `dl_list_workbooks`,
   `dl_get_workbook_entries`, `dl_snapshot_dashboard`, `dl_read_object`, and
   `dl_get_entries_relations` as required by the target.
3. Use `dl_reference` for bounded chart/API/tool-selection guidance.
4. Build a create or update plan with `dl_plan_object_create` or
   `dl_plan_object_update`.
5. For dataset-model changes use `dl_plan_guarded_dataset_update`; for a
   single dashboard tab use `dl_plan_dashboard_tab_update`.
6. Validate with `dl_validate_object`, optional
   `dl_validate_editor_runtime_contract`, and `dl_validate_project`.
7. Compile `dl_build_payload_plan` and an unapproved
   `dl_create_safe_apply_plan`.
8. Execute only after approval and runtime gates, then require saved readback.
9. Build publish only with `dl_create_publish_from_saved_plan`; finish with
   published readback and runtime/browser evidence for visible changes.

New standard charts are Wizard-first. Updates preserve technology and
visualization ID from fresh saved readback. Advanced Editor requires an
explicit request or registered capability gap. QL requires a direct QL request
and is never an automatic fallback.

## Project-live manifest workflow

Use this lane only when a downstream repository already owns guarded commands
for dry-run, save, publish, or an explicit retire lifecycle.

1. `dl_detect_project_live_workflows` looks for `.datalens-mcp.json`,
   `datalens-mcp.project.json`, `.datalens-mcp.yaml`, or `.datalens-mcp.yml`.
   A missing manifest returns `adapter_required`.
2. `dl_plan_project_manifest` previews a dry-run-only manifest. It writes the
   file only after explicit approval.
3. `dl_plan_project_live_workflow` returns exact argv, target IDs, allowed env
   names, expected artifacts, evidence checks, and blockers without execution.
4. `dl_run_project_live_dry_run` runs only the manifest-declared command when
   `execute_now=true`; it uses an allowlisted environment and redacts captured
   output.
5. `dl_read_project_live_summary` parses the declared JSON summary and blocks
   missing or zero-coverage evidence.
6. `dl_run_project_live_apply` additionally requires approval, live write/save
   gates, and manifest publish allowance when publishing is requested.
7. Read the summary again after execution and keep saved, published, and
   browser/runtime proof distinct.

The manifest is not a generic script runner. It must declare exact object IDs,
commands, environment names, expected artifacts, and safety constraints.

## Named object removal

Delete, move, and permission operations are blocked in normal project actions.
When the user directly asks to remove named unnecessary objects, use a separate
`retire_legacy_objects` manifest action. It requires exact object IDs/types,
workbook ID, reason, user-decision provenance, relation-graph proof, saved and
published no-reference proof, dry-run retire plan, approval, execution summary,
and post-retire readback.

Never hide removal flags inside a normal publish action.

## Evidence checklist

Before a live save:

- the target and affected object IDs are explicit;
- fresh saved readback exists;
- object/project validation has non-zero coverage;
- payload and safe-apply plans identify methods, overlays, and blockers;
- no credential value appears in project artifacts;
- readback mode and deployment-report path are declared.

After execution:

- saved and published readbacks are separate artifacts;
- each report states its proof level;
- visible changes have browser/runtime proof or explicit
  `runtime_not_verified`/`runtime_failed` status;
- no `done` claim is based on static validation or API readback alone.
