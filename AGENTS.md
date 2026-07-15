# AGENTS.md

## Scope

This repository contains the local `datalens-dev-mcp` Python MCP stdio server.

The server is a client-independent MCP interface for DataLens dashboard development: governance, Editor authoring, API planning, guarded safe apply, project workflow, visual QA, read-only diagnostics, and operator context. It runs locally over stdio and can be connected to Codex, Claude, or another MCP client.

## Read Order

1. `AGENTS.md`
2. `README.md`
3. `README_ru.md`
4. `docs/policy_vocabulary.md`
5. `docs/mcp/codex_connection.md`
6. `docs/codex_setup.md`
7. `docs/configuration.md`
8. `docs/local-only-safety-model.md`
9. `docs/route-policy.md`
10. `docs/safe-apply.md`
11. `docs/mcp/tools.md`
12. `docs/mcp/response_contracts.md`
13. `docs/source_provenance.md`

## Local Material Policy

- Runtime behavior must live in MCP-native code, configs, schemas, templates, examples, tests, and distilled docs.
- Raw source materials, long copied pages, course/book extracts, and full extraction artifacts do not belong in the tracked repo.
- Keep only compact, attributable runtime registries, distilled rules, configs, schemas, templates, curated examples, and tests.
- Do not commit actual IAM tokens, env files, auth headers with live secrets, passwords, private keys, or credential material.

## Route And Write Safety

- Default DataLens behavior remains read-only.
- Writes require explicit enablement, approved safe apply, fresh read/revision preservation, `save` semantics, readback, and a deployment report.
- Canonical chart creation routes are `wizard_native`, `editor_advanced`, `editor_table`, `editor_markdown`, `editor_js_control`, and explicit-only `ql_explicit`. `wizard_map_native` remains a compatibility alias for `wizard_native` with `visualization_id=geolayer`.
- New standard KPI, table, pivot, line, area, column, bar, combined, pie/donut, scatter/bubble, treemap, and map charts use Wizard. JavaScript/Editor is selected only by an explicit request or a registered capability gap. Updates preserve the technology and visualization ID from fresh saved readback.
- QL read/create/update remains available only when the user directly requests QL. QL must never be selected automatically, used as a fallback, or generated from a general prompt; QL delete remains closed.
- Do not add `d3_node`, regular Editor Chart, Gravity UI Charts, runtime route fallback, guessed IDs, delete/move/permission operations, blind writes, or publish outside the delivery-intent state machine.
- For implementation/fix/enhance/redesign requests against known targets, Codex/tool approval plus guarded write/save/publish gates is enough to proceed through save, saved readback, publish from saved readback, and published readback; draft, review, plan-only, save-only, and no-publish instructions still block publish.

## Verification

Run the offline gate:

```bash
python3 scripts/run_offline_acceptance.py
```
