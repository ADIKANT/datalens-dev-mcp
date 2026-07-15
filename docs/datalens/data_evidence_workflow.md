# Data Evidence Workflow

This workflow standardizes read-only schema and data evidence before dashboard
planning, SQL changes, dataset updates, and DQ conclusions.

Use neutral evidence wording in reports: `read-only metadata/data evidence
provider`, `schema probe`, and `bounded data probe`. Do not name local helper
implementations in user-facing docs or reports.

## Evidence Statuses

- `AVAILABLE`: targeted evidence confirms the table/source exists.
- `UNAVAILABLE_CONFIRMED`: targeted `table_discovery` evidence confirms absence.
- `NOT_PROBED`: no targeted evidence has been collected.
- `PROBE_BLOCKED`: the requested probe is unsafe, incomplete, or unavailable.
- `INCONCLUSIVE_TRUNCATED`: an aggregate inventory is truncated and cannot prove
  absence.

## Standard Probe Operations

- `table_discovery`: targeted `information_schema` or `system.tables` table
  existence probe.
- `column_list`: targeted column list probe.
- `bounded_row_count`: row count with explicit bounds where applicable.
- `bounded_sample`: sample with explicit columns and a maximum row limit.
- `cte_stage_count`: count rows at a named CTE stage.
- `link_direction`: classify source-side, target-side, and bidirectional graph
  table evidence.
- `source_freshness_availability`: row-count and max-timestamp evidence.

Production probes must not use `SELECT *`; enumerate columns explicitly. If the
provider cannot execute the probe, record `PROBE_BLOCKED` with the missing
capability and next step.

## MCP Tools

1. `dl_build_data_evidence_probe_plan` creates a read-only probe plan and SQL
   contract. It does not execute queries.
2. `dl_record_data_evidence` records sanitized provider output under the project
   in `reports/data_evidence/` and appends a compact requirements note.
3. `dl_evaluate_data_evidence` decides whether table availability can be stated.
   A truncated aggregate inventory never proves absence; targeted
   `table_discovery` evidence is required for `UNAVAILABLE_CONFIRMED`.

Evidence artifacts belong inside the active project, not in raw material
folders or global MCP documentation.
