# MCP tools

[Русский](tools.md) · **English** · [Project home](../README_en.md)

[Quick start](../README_en.md#quick-start) · [DataLens access](access_en.md) · [Connect](codex_setup_en.md) · **Tools** · [Workflows](usage-flow_en.md) · [Sources](sources_en.md) · [Safety](local-only-safety-model_en.md)

The default `autonomous-v2` surface contains eight task-level tools and keeps internal lifecycle calls out of the model context. The server selects the safe route, maintains a restart-safe journal, creates a hash-bound plan, executes it through Safe Apply, and returns compact results with evidence resource URIs.

The exact JSON schema is always available through MCP `tools/list`. Technical contracts and the compatible `legacy-v1` surface are documented in the [catalog](mcp/tools.md); common responses are in [response contracts](mcp/response_contracts.md).

## Autonomous surface

| Tool | Purpose | When to use | Required data | Result and class | Source |
| --- | --- | --- | --- | --- | --- |
| `dl_task_start` | Compile a request into an immutable contract and start its workflow | At the beginning of a new task | `request` plus optional `project_root`, `context`, and `run_until` | Task ID, state, performed transitions, and resource URI · `local` | [Task workflow](usage-flow_en.md#autonomous-task-workflow) |
| `dl_task_resume` | Resume a persisted workflow with optimistic checks | After restart or a plan/blocker boundary | `task_id`, expected state/hash, and execution boundary | New state and compact outcome · `local`/`guarded write` | [Task workflow](usage-flow_en.md#autonomous-task-workflow) |
| `dl_task_status` | Read compact state without executing transitions | Check progress | `task_id` | State, revision, etag, blocker, and next action · `local` | [Task state](mcp/response_contracts.md#task-level-responses) |
| `dl_inspect` | Collect a bounded project and artifact overview | Before planning or during diagnosis | Optional `task_id`, `target_url`, and `max_nodes` | Bounded graph and project-validation summary · `local` | [Task workflow](usage-flow_en.md#autonomous-task-workflow) |
| `dl_plan` | Advance a task to a validated hash-bound plan | Require an explicit plan before execution | `task_id` | Plan hash, resource URI, and readiness · `local` | [Safe Apply](safe-apply_en.md) |
| `dl_execute` | Execute only the exact validated plan | After checking `plan_hash` | `task_id`, `plan_hash`, and an exact token for destructive scope | Save/readback/publish/QA transition result · `guarded write` | [Safe Apply](safe-apply_en.md) |
| `dl_verify` | Check the requested proof target | After planning or execution | `task_id` and optional `proof_target` | Journal, readback, and browser-policy checks · `local` | [Task state](mcp/response_contracts.md#task-level-responses) |
| `dl_evidence` | Read one bounded task artifact | Inspect a plan, receipt, or evidence fragment | `task_id`, resource URI/section/offset/limit | Bounded excerpt without a heavy inline response · `local` | [Evidence resources](mcp/response_contracts.md#task-level-responses) |

## Surface profiles

- `autonomous-v2` is the default: eight tools, at most 9 KB in `tools/list`, and at most 1.5 KB of initialization instructions.
- `legacy-v1` preserves the previous 39 lifecycle tools for existing integrations.
- `expert` exposes the complete internal registry for operator-controlled diagnostics. Only the local process setting `DATALENS_MCP_TOOL_SURFACE=expert` can enable it; a request or prompt cannot change the profile of a running server.

Acceptance receipts record `declared_surface`, `effective_surface`, and
`surface_consistent`. The autonomy, affected, and full-sharded profiles always
run as `autonomous-v2`; `legacy-v1` compatibility is exercised only by
explicitly isolated tests.

Restart the MCP process after changing `DATALENS_MCP_TOOL_SURFACE`. Do not pass a profile to `tools/list`; the process fixes its active surface at startup.

## Execution safety

- The task contract, state, and event chain persist under `.datalens-mcp/tasks/<TASK_ID>/` and are verified during replay.
- `dl_execute` accepts only the plan hash bound to the immutable task contract.
- A write task uses the normal save-first Safe Apply, saved readback, publish from verified saved state, and published readback.
- Review, audit, diagnose, and plan-only requests do not write.
- Heavy plans and evidence are returned as `datalens://tasks/<TASK_ID>/...`; `dl_evidence` reads only one allowed size-bounded artifact.
- A separate destructive token is required only for explicitly compiled destructive scope. Arbitrary whole-object deletion remains unsupported.

## Compatibility

The internal lifecycle tools were not removed: `legacy-v1` preserves the exact previous set of 39 names and schemas. New clients should use `autonomous-v2`; a direct call to a hidden low-level tool in this profile is rejected before execution.
