# AGENTS.md

## Scope

This repository is a local DataLens dashboard development workspace managed by `datalens-dev-mcp`.

## Read Order

1. `AGENTS.md`
2. `memory-bank/profile.md`
3. `memory-bank/context-index.md`
4. `memory-bank/project-brief.md`
5. `memory-bank/active-context.md`
6. `memory-bank/progress.md`
7. `memory-bank/requirements-ledger.md`
8. Task-specific dashboard, mapping, artifact, baseline, and readback files.

## Safety

- Read-only and dry-run-first by default.
- Writes require explicit environment enablement, an approved safe apply plan, fresh read, save mode, readback, and deployment report.
- Do not guess IDs, delete, move, change permissions, or publish outside the delivery-intent state machine.
- Planning/review intents do not publish. Known live implementation/fix/enhance/redesign targets continue through save, saved readback, publish from saved readback, and published readback when Codex/tool approval and guarded runtime gates are present. Draft, save-only, and no-publish instructions stop after saved readback.
- Use canonical policy vocabulary from `docs/policy_vocabulary.md`: project-live, zero evidence, delivery-intent, retire_legacy_objects, manifest summary, hidden/internal compatibility tools, connector/connection, proof levels, current docs/API reconciliation, and golden runtime gallery.

## Chart Routing

- New standard charts use `wizard_native`; `wizard_map_native` is accepted only as the `geolayer` compatibility alias.
- Existing objects preserve their technology and visualization ID from fresh saved readback.
- Use JavaScript only by explicit request or registered capability gap.
- Use `ql_explicit` only after a direct user request with explicit payload or fresh saved seed. Never choose QL automatically or as fallback; QL delete remains closed.
