# Project Workflow

Use this workflow from an MCP client while working inside a downstream
DataLens project folder. Project artifacts are created only when the operator
selects a specific project root.

## Start A Project Workspace

Call `dl_start_pipeline` with the project path and scenario:

```json
{
  "project_root": "<PROJECT_ROOT>",
  "scenario": "new_dashboard",
  "dashboard_name": "<Dashboard Name>"
}
```

First call Project Memory Bank `memory_context` and pass its
`project_context_ref.v1` as `context_ref` to project-aware DataLens tools.
`datalens-dev-mcp` does not scaffold, read, or update `AGENTS.md` or
`memory-bank/**`; its responses return evidence references and bounded record
suggestions for the coordinating plugin.

## Intake Requirements

Use the requirements workspace as the source of truth:

1. `dl_init_requirements_workspace`
2. `dl_ingest_requirements_markdown` for requirements, S2T notes, comments, and
   user decisions
3. `dl_ingest_requirements` when compact requirements and optional CSV evidence
   should also produce a dashboard brief and data contract
4. `dl_update_user_decision` when the user confirms a route, metric, selector,
   or layout choice

Missing requirements must produce targeted questions. Do not invent workbook,
dashboard, chart, dataset, or connection IDs.

## Map The Dashboard

Build the project plan in this order:

1. `dl_build_governance_brief`
2. `dl_select_dashboard_blueprint`
3. `dl_populate_dashboard_map_canvas`
4. `dl_build_dashboard_blueprint_plan`
5. `dl_create_connector_plan`
6. `dl_create_dataset_plan`
7. `dl_create_dataset_field_plan`
8. `dl_validate_chart_plan_against_requirements`

The generated requirements files keep dashboard sections, metrics, attributes,
selectors, object relations, assumptions, and open questions visible.

## Choose Chart Routes

Route policy is deterministic:

- use `wizard_native` for new standard KPI, table/pivot, line/area, bar/column,
  combined, pie/donut, scatter/bubble, treemap, and map charts;
- preserve an existing object's technology and visualization ID from fresh
  saved readback;
- use Advanced Editor JavaScript only by explicit request or registered
  capability gap; keep Markdown and JS controls on their dedicated routes;
- use `ql_explicit` only after a direct QL request with explicit payload or a
  fresh saved QL seed; never select it automatically;
- do not create regular Editor charts, guessed-ID plans, hidden
  delete/move/permission plans, runtime route fallbacks, or blind writes.
  Publish is handled only by the delivery-intent safe-apply/readback lane.

## Request Legacy Object Removal

If a project needs to remove named unnecessary DataLens objects, do
not add `--delete-legacy`, `delete-*`, direct `deleteEditorChart` /
`deleteDashboard`, move operations, or permission mutation flags to normal
dry-run, save, or publish workflows. Add a separate `retire_legacy_objects`
action to `.datalens-mcp.json`.

The retire action must declare exact object ids and types, workbook id, reason,
the user request quote or decision id, relation graph proof, saved and
published no-reference proof, dry-run retire plan, approval provenance,
execution summary, and post-retire readback. Use
`dl_plan_project_live_workflow` with `action=retire_legacy_objects` first, then
run only after explicit approval and live write flags.

## Generate Templates And Payload Plan

For Advanced Editor routes, call:

1. `dl_generate_editor_bundle`
2. `dl_validate_project`
3. `dl_build_payload_plan`
4. `dl_create_safe_apply_plan`

For standard native charts, call `dl_build_wizard_payload_template` with
`wizard_native`, the canonical visualization ID, dataset, semantic field
bindings, and a location XOR. Prefer a fresh saved seed with the same
visualization ID; otherwise use the committed canonical template. Validate
before any live save. `wizard_map_native` remains an accepted `geolayer` alias.

## Safe Apply Save-Only

Writes are blocked unless all gates are present:

- `DATALENS_MCP_ENABLE_WRITES=1`
- explicit safe-apply approval
- fresh read and revision preservation
- `mode=save`
- readback mode `minimal` or `full`
- deployment report

Runtime startup is read-only and planning/review intents never publish. For
live implementation, fix, or enhance requests with known target IDs, explicit
write gates, approved safe apply, saved readback, and no draft/no-publish
instruction, delivery continues through publish from saved readback and
published readback.

## Readback And Catalog

After validation or a saved live apply, call `dl_readback_and_report`. When
chart bundles or object relations exist, the workflow also updates local
implemented-chart artifacts under the project root:

- `docs/datalens/implemented_charts.md`
- `artifacts/reports/implemented_charts_catalog.md`
- `requirements/charts.md`
- `requirements/metrics.md`
- `requirements/object_relations.md`

Use these files as the project-specific implementation record.

## Dry-Run Checklist

Before asking for a live save:

- `dl_validate_project` returns `status=pass`.
- `dl_build_payload_plan` lists the intended workbook and local payload files.
- `dl_create_safe_apply_plan` is unapproved until the user approves it.
- `dl_readback_and_report` records `write_executed=false` for offline runs.
- No credential value appears in project artifacts.

## Migrate Legacy Direct-RPC Projects

For existing projects with standalone DataLens scripts, start with
`dl_detect_project_adapter`. Direct-RPC-only projects are quarantined by
default: MCP does not execute them unless a local manifest declares argv
commands, exact workbook/dashboard IDs, summary paths, branch status, changed
counts, target IDs, evidence checks, and safe constraints.

Use the migration-adapter guide and the sample manifests in
`templates/project_live_workflows/`. New migration manifests must keep
`may_execute_command: false` until dry-run evidence has been reviewed.

## Project-Live Manifest Workflow

For custom project-live layouts, use exact tools and artifacts:

1. `dl_detect_project_live_workflows` reads `.datalens-mcp.json`,
   `datalens-mcp.project.json`, `.datalens-mcp.yaml`, or `.datalens-mcp.yml`.
   Without a manifest it returns `adapter_required` and a suggested manifest.
2. `dl_plan_project_manifest` previews a dry-run-only manifest when a manifest
   is missing; it writes only with approval.
3. `dl_plan_project_live_workflow` returns the action command argv, manifest
   `summary_path`, workbook/dashboard IDs, affected object groups, required env
   names, rejected env declarations, evidence checks, safety constraints, and
   blocked reasons.
4. `dl_run_project_live_dry_run` executes only the manifest-declared dry-run
   command when `execute_now=true`, the manifest allows execution, and stdout or
   stderr can be redacted.
5. `dl_read_project_live_summary` parses the manifest summary JSON. It must
   report target IDs, changed object counts, branch status, evidence paths,
   remaining drift, dashboard preflight, SQL lint coverage, and any
   `zero_coverage` blockers from zero evidence.
6. `dl_run_project_live_apply` runs save/apply only after approval and live
   write flags. Publish additionally requires manifest `allow_publish=true`,
   `DATALENS_MCP_LIVE_ALLOW_PUBLISH=1`, saved readback evidence, a
   publish-from-saved plan, and published readback.

Normal workflows never smuggle deletion into publish. Named unnecessary objects
use `action=retire_legacy_objects` with exact IDs and the retire lifecycle
proof artifacts listed above.
