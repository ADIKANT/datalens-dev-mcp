# Project Migration Adapter

This adapter helps downstream projects move from standalone
direct-RPC scripts to manifest-backed MCP workflows. It does not edit live
dashboards by itself.

## Adapter Taxonomy

`dl_detect_project_adapter` classifies a project into one of these rules:

| Adapter | Status | Next step |
| --- | --- | --- |
| `standard_bundle` | supported | Use `dl_validate_project`, `dl_build_payload_plan`, `dl_create_safe_apply_plan`, and readback. |
| `repo_live_workflow_manifest` | supported | Use `dl_detect_project_live_workflows`, plan the selected action, dry-run, validate summary, then gated save/publish. |
| `dataset_update_workflow` | adapter required | Wrap `validateDataset` / `updateDataset` scripts in a manifest with target IDs, changed counts, and readback evidence. |
| `advanced_editor_project` | adapter required | Bind Editor source files to exact chart/dashboard IDs and require payload preflight before save. |
| `legacy_direct_rpc_quarantine` | quarantined | Do not execute direct-RPC scripts through MCP until a manifest declares safe actions and evidence. |
| `unknown_custom_layout` | adapter required | Add a manifest or convert to the standard MCP bundle layout before live write planning. |

Direct-RPC scripts are inventory evidence only. MCP execution is available only
through manifest-declared argv commands and remains blocked while
`may_execute_command` is false.

## Required Manifest Contract

New migration manifests start dry-run only:

```json
{
  "may_execute_command": false,
  "allow_publish": false
}
```

Every migration manifest must declare:

- target `workbook_id` and `dashboard_ids`;
- action-specific `command` argv arrays;
- action-specific `summary_path` values;
- `evidence_checks`;
- summary requirements for `branch_status`, `changed_object_counts`,
  `target_ids`, and `evidence_paths`;
- expected changed object groups;
- affected target IDs;
- safe constraints that keep delete, move, and permission mutations out of
  normal validate, dry-run, save, publish, and readback actions.

Sample manifests:

- `templates/project_live_workflows/dry_run_manifest.json`
- `templates/project_live_workflows/validate_summary_manifest.json`
- `templates/project_live_workflows/save_manifest.json`
- `templates/project_live_workflows/saved_readback_manifest.json`
- `templates/project_live_workflows/publish_manifest.json`
- `templates/project_live_workflows/published_readback_manifest.json`

## Helper Flow

1. Run `dl_detect_project_adapter`.
2. If no manifest exists, run `dl_detect_project_live_workflows` or
   `dl_plan_project_manifest` to preview a dry-run-only manifest.
3. Add exact workbook/dashboard IDs and keep `may_execute_command: false`.
4. Run `dl_plan_project_live_workflow` for `action=dry_run`.
5. Execute dry-run only after reviewing the manifest command and only when the
   manifest explicitly allows execution.
6. Run `dl_read_project_live_summary` for `action=dry_run`; the summary must
   include branch status, changed counts, target IDs, and evidence paths.
7. Enable save only after dry-run summary validation passes.
8. Run saved readback and validate saved evidence before publish.
9. Enable publish only after saved readback exists and the manifest explicitly
   allows publish.
10. Run published readback and keep the adoption report compact inline, with
    detailed evidence stored under project artifacts.

## Adoption Report Contract

Inline adoption reports should stay compact:

- adapter;
- status;
- detected file count;
- blocked operations;
- next action;
- artifact path.

Detailed scans belong in an artifact such as
`artifacts/project_migration_adapter_report.json`; do not paste long script
contents into chat or tracked docs.
