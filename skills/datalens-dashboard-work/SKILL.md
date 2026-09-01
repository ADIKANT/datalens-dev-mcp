---
name: datalens-dashboard-work
description: Create, inspect, diagnose, update, publish, and verify Yandex DataLens dashboards and charts through the DataLens MCP. Use for ordinary DataLens project work, including Wizard, Advanced Editor or JavaScript, formulas, data errors, references, visual corrections, and saved or published readback. Do not use for maintaining, testing, releasing, or modifying the datalens-dev-mcp server itself.
---

# DataLens dashboard work

Work from the exact dashboard project or subproject. Do not inspect the MCP server source or run its tests during ordinary dashboard work.

1. Call `dl_task_start` with the user's request and exact project root. Prefer the manifest target and live discovery over guessed IDs.
2. Read the returned `execution_brief`. Treat its task kind, target, reference, technology, preservation rules, delivery, missing fields, and `next_call` as authoritative.
3. If `missing_fields` names semantic changes, provide only the typed changes needed for those fields through `dl_task_resume`. For an ordinary follow-up, pass plain text in `follow_up`; do not invent a relationship enum or revision.
4. Open detailed MCP knowledge only when needed:
   - `datalens://knowledge/formulas`
   - `datalens://knowledge/wizard-authoring`
   - `datalens://knowledge/javascript-editor-authoring`
   - `datalens://knowledge/chart-selection`
   - `datalens://knowledge/error-diagnosis`
   - `datalens://knowledge/save-publish-lifecycle`
5. If `confirmation_required` is true, show a short plan with target, changes, preservation, and publish effect, then wait for one confirmation. After confirmation call the unchanged, fully populated `next_call`.
6. Verify saved readback, publish only from verified saved state when requested, then verify published readback. Run data diagnostics only when the brief says data is impacted.
7. Use Browser only for final read-only visual acceptance after published readback. Never use it for discovery or mutation.

Never expose credentials, change permissions, write to production or unowned objects, guess IDs, switch an existing chart's technology because of an error message, or use QL unless the user directly requested QL.
