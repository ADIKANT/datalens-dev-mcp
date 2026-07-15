# AGENTS.md

## Scope

This repository contains the local `datalens-dev-mcp` Python MCP stdio server.

The server is a client-independent MCP interface for DataLens dashboard development: object discovery, planning, validation, guarded save and publish, project workflows, visual QA, diagnostics, and operator context. It runs locally and can be connected to Codex, Claude, or another MCP client.

## Read Order

1. `AGENTS.md`
2. `README.md`
3. `README_en.md`
4. `docs/README.md`
5. `docs/access.md`
6. `docs/codex_setup.md`
7. `docs/usage-flow.md`
8. `docs/configuration.md`
9. `docs/local-only-safety-model.md`
10. `docs/route-policy.md`
11. `docs/safe-apply.md`
12. `docs/tools.md`
13. `docs/mcp/tools.md`
14. `docs/mcp/response_contracts.md`
15. `docs/sources.md`
16. `docs/source_provenance.md`

## Local Material Policy

- Runtime behavior lives in MCP code, configs, schemas, templates, examples, tests, and distilled documentation.
- Raw source corpora, long copied pages, course or book extracts, and complete extraction artifacts do not belong in the tracked repository.
- Keep compact attributable registries, distilled rules, schemas, templates, curated examples, and tests.
- Never commit IAM tokens, env files, live authorization headers, passwords, private keys, or other credential material.

## Route And Write Safety

- The standard runtime follows the user request. Audit, review, diagnose, and plan-only requests do not write. Save-only and no-publish stop after saved readback. Create, fix, update, enhance, and redesign requests for known targets continue through save, saved readback, publish from saved state, and published readback.
- Write, save, and publish capabilities are enabled by default. An explicit environment value of `0` is a hard-off switch for the corresponding capability.
- Do not ask for another confirmation before ordinary save or publish after the user has requested the change. Deleting a complete DataLens object is the only operation that requires a separate confirmation with exact IDs and an unchanged plan.
- Every write requires a known target, fresh saved readback, target and revision checks, payload validation, unknown-field preservation, save-first behavior, and readback. Publish is built only from verified saved state.
- Removing a legend, filter, column, tab, or widget inside an object is an update. Object moves, permission changes, and credential mutations are unsupported.
- Canonical chart creation routes are `wizard_native`, `editor_advanced`, `editor_table`, `editor_markdown`, `editor_js_control`, and direct-request-only `ql_explicit`. `wizard_map_native` is normalized to `wizard_native` with `visualization_id=geolayer`.
- New standard KPI, table, pivot, line, area, column, bar, combined, pie/donut, scatter/bubble, treemap, and map charts use Wizard. JavaScript/Editor is selected by direct request or a documented capability gap. Updates preserve technology and visualization ID from fresh saved readback.
- QL read/create/update is used only after a direct QL request. Never select QL automatically, use it as a fallback, or generate it from a general prompt. Whole-object QL deletion remains unsupported.
- Do not guess IDs, perform blind writes, or publish outside the saved-readback flow.

## Verification

Run the offline gate:

```bash
python3 scripts/run_offline_acceptance.py
```
