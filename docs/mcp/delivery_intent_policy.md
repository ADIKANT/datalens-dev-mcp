# Delivery Intent Policy

The MCP server uses one delivery state machine for pipeline planning,
project-live workflow planning, safe apply, and publish-from-saved planning.
Delivery language is intent, not permission. Runtime writes still require
enablement, approved safe apply, fresh read/revision preservation, save
semantics, readback, and a deployment report.

States:

- `read_only`: review, audit, diagnose, inspect, check, and unknown intents.
- `plan_only`: plan-only and dry-run requests.
- `save_only`: draft, save-only, and no-publish requests after save gates.
- `save_then_publish`: implementation, fix, enhance, redesign, or update
  requests with known target IDs, Codex/tool approval, write/save/publish gates,
  and no draft/no-publish instruction.
- `publish_from_saved`: the guarded publish operation built from fresh
  saved-branch readback.
- `blocked`: missing target lock, missing runtime gates, missing approval,
  stale saved readback, or destructive/move/permission-like operations.

Every production plan that resolves delivery intent returns
`delivery_intent_decision` with `state`, `reason`, `required_gates`,
`satisfied_gates`, `next_action`, and `proof_path`. Compatibility fields such
as `intent`, `publish_expected`, `target_branch`, and `next_actions` may also be
present.

For live implementation, fix, or enhance requests with known target IDs,
explicit write gates, approved safe apply, saved readback, and no
draft/no-publish instruction, delivery proceeds through save, saved readback,
publish from saved readback, and published readback. The original user request
plus Codex/tool approval is sufficient operator approval; no additional literal
chat phrase such as `I approve` is required.

Publish and save remain separate internal operations. Publish must be built from
a fresh saved-branch artifact, preserve expected `revId` and `savedId`, and
prove published readback after execution. Draft, review, plan-only, save-only,
and no-publish instructions block publish. Unknown target IDs block writes; do
not guess workbook, dashboard, chart, dataset, or connection IDs.
