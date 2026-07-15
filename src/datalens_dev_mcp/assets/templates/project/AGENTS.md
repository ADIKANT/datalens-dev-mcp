# AGENTS.md

## Scope

This directory is a DataLens dashboard workspace managed through `datalens-dev-mcp`.

## Read Order

1. `AGENTS.md`
2. `memory-bank/profile.md`
3. `memory-bank/context-index.md`
4. `memory-bank/project-brief.md`
5. `memory-bank/active-context.md`
6. `memory-bank/progress.md`
7. `memory-bank/requirements-ledger.md`
8. Task-specific requirements, mappings, snapshots, plans, and readbacks.

## Delivery Rules

- Follow the user's requested mode. Audit, review, diagnose, and plan-only tasks do not write. Save-only and no-publish stop after saved readback. Create, fix, update, enhance, and redesign tasks continue through save, saved readback, publish from saved state, and published readback.
- Do not ask for another confirmation before ordinary save or publish after the user has requested the change.
- Deleting a complete DataLens object requires a separate confirmation with exact IDs and an unchanged plan. Removing content inside an object is an update.
- Before every write, confirm the exact target, read current saved state, preserve revision and unknown fields, validate the payload, save first, and read back the result.
- Publish only from verified saved state. Keep saved and published readbacks separate.
- Do not guess IDs, move objects, change permissions, mutate credentials, or perform blind writes.

## Chart Routing

- New standard charts use `wizard_native`; `wizard_map_native` is normalized to `wizard_native` with `visualization_id=geolayer`.
- Existing objects preserve technology and visualization ID from current saved readback.
- Use JavaScript/Editor after a direct request or for a documented capability gap.
- Use `ql_explicit` only after a direct QL request with an explicit payload or current saved seed. Never choose QL automatically or after another route fails.
