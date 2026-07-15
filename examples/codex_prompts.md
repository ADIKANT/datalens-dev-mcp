# Codex Prompt Examples

Use these prompts from a Codex thread that has the `datalens-dev` MCP server
connected.

## New Dashboard From Requirements

```text
Use the datalens-dev MCP for <PROJECT_ROOT>/<project>.
Initialize the project workspace, ingest these dashboard requirements, build
the dashboard map/canvas, plan connectors/datasets/fields, choose allowed chart
routes, generate templates, validate the project, and stop after a dry-run
payload and safe-apply plan. Do not execute writes.

Requirements:
<paste compact requirements or S2T notes>
```

## Improve Existing Dashboard

```text
Use the datalens-dev MCP for <PROJECT_ROOT>/<project>.
Load the existing project context and requirements workspace, ingest these user
comments, update the dashboard map/canvas and chart plan, regenerate only the
affected template bundle, validate, and produce a safe-apply save plan. Keep
publish out of scope.

User comments:
<paste comments>
```

## Explain Workbook Object Relations

```text
Use the datalens-dev MCP in read-only mode. Read workbook <WORKBOOK_ID>, list
entries, explain dashboard/chart/dataset/connection relations, and identify
missing selector targets or object-relation risks. Do not write or publish.
```

## Preserve Or Explicitly Migrate A Wizard Widget

```text
Use the datalens-dev MCP for <PROJECT_ROOT>/<project>.
Inspect the widget requirements and current route evidence. If the widget is a
Wizard chart, preserve its technology and visualization ID from fresh saved
readback. Plan Advanced Editor JavaScript only if I explicitly request the
migration and the capability gap is registered. Generate only a dry-run bundle
and validation report.
```

## Dry-Run Payload Plan Only

```text
Use the datalens-dev MCP for <PROJECT_ROOT>/<project>.
Do not call live write tools. Build or refresh the payload plan and safe-apply
plan from existing project artifacts, then report the exact files and blocked
write gates.
```
