# Direct typed workflow

The agent carries the user's task; the MCP exposes typed reads, authoring and mutation services. There is no task compiler, immutable execution plan, generic command gateway or task-resume engine in the current interface. Use the active tools' schemas and the [five domain skills](../skills/datalens-inspect/SKILL.md) for routing.

A normal change starts with the exact project/target and fresh state, uses the relevant typed authoring or update operation, validates, saves and checks saved readback. Publish only within the requested scope from the verified saved revision, then inspect published readback when that object type has a publish phase. Operation receipts preserve uncertain effects across process restarts; inspect status and reconcile rather than replaying a write.

[Authorized scope and delivery](../skills/datalens-dashboard/references/authorized-scope.md) is the canonical owner for authorization, continuation, changed scope and multi-workbook completion. Reuse its short handoff in existing project context when needed; ordinary reads do not require new files.

API readback, bounded dataset preview, static source checks and Browser render prove different things. Preview uses current GUID/schema bindings and bounded data; an empty result does not prove an empty source. A visual task retains read-only Browser verification after API and relevant data checks. Preserve explicit no-browser constraints and mark the unverified visual level accurately.

For task-sized host evaluation and controlled live proof see [acceptance boundaries](public-autonomy-canary.md). Local regressions and package smoke do not prove model behavior, live provider writes or rendered/business acceptance.
