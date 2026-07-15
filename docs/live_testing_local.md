# Local Live Testing

This repo is a local stdio MCP server. Live checks are manual, opt-in, and use
local DataLens credentials only in the operator environment.

## Read-Only Smoke

Default command:

```bash
python3 scripts/live_smoke_readonly.py
```

Without an explicit live flag the script exits with a skipped JSON result. It
does not read credentials, write objects, publish objects, or print token
values.

Opt-in read-only command:

```bash
DATALENS_MCP_RUN_LIVE_TESTS=1 \
DATALENS_ORG_ID=<ORG_ID> \
DATALENS_IAM_TOKEN=<IAM_TOKEN> \
python3 scripts/live_smoke_readonly.py
```

Optional read targets:

```bash
DATALENS_MCP_LIVE_WORKBOOK_ID=<DISPOSABLE_WORKBOOK_ID>
DATALENS_MCP_LIVE_OBJECT_TYPE=<dashboard|editor_chart|wizard_chart|dataset|connector>
DATALENS_MCP_LIVE_OBJECT_ID=<OBJECT_ID>
DATALENS_MCP_LIVE_OBJECT_BRANCH=<saved|published>
```

The script performs:

- read-only auth probe through `getWorkbooksList`;
- workbook list read;
- optional workbook entries read when `DATALENS_MCP_LIVE_WORKBOOK_ID` is set;
- optional object read when object type and ID are set;
- dashboard planning in a temporary directory without writes.

It prints credential presence booleans only. It never prints IAM token values,
auth headers, token prefixes, token lengths, or full object payloads.

## Disposable Save Rule

No live write can happen through `scripts/live_smoke_readonly.py`.

Manual save testing is allowed only when all of these are true:

- the target is disposable, not a production workbook or production object;
- `DATALENS_MCP_ENABLE_WRITES=1` is set for the process executing
  `dl_execute_safe_apply`;
- `DATALENS_MCP_LIVE_ALLOW_SAVE=1` is set as the operator confirmation;
- the safe-apply plan is approved and records a fresh read, revision
  preservation, `mode=save`, and minimal readback.

Do not set default workbook IDs to production objects in local config. Keep
production IDs as explicit per-call inputs when read-only inspection is needed.

### Disposable Save Checklist

Before a save-only live check, record these values in the operator notes or
deployment report:

- disposable workbook ID;
- disposable object ID or planned new object name;
- safe-apply plan path;
- fresh read branch and revision;
- approval source;
- expected saved readback target;
- rollback or cleanup owner.

## Publish Rule

Runtime startup and read-only live smoke never publish. A publish action is
never part of the read-only smoke.
Planning/review intents never publish. For a live implementation, fix, or
enhance request with known target IDs and no draft/no-publish instruction,
publish is the guarded continuation after saved readback. It requires:

- a publish-from-saved plan approved through the Codex/tool call;
- `DATALENS_MCP_ENABLE_WRITES=1`;
- `DATALENS_MCP_LIVE_ALLOW_SAVE=1`;
- `DATALENS_MCP_LIVE_ALLOW_PUBLISH=1`;
- a disposable target or an explicitly requested live production change.

The required sequence is save, saved readback, publish from saved readback, and
published readback.

Published readback is not browser proof. Delta v7 completion requires a
runtime gate artifact for changed runtime objects unless the task is explicitly
non-rendering. If browser tooling is unavailable, unauthenticated, or times
out, the final maintenance handoff must report `runtime_not_verified`, not
`done`. If the browser or console evidence contains Data fetching error,
Unknown field, non-existent field, `DB::Exception`, `ILLEGAL_AGGREGATION`,
`ERR.DS_API.FIELD.NOT_FOUND`, missing DB columns, `502 Bad Gateway`, or
`UNKNOWN_TABLE`, the runtime gate is blocking evidence.

### Publish Manual Checklist

Before any publish action, verify:

- saved readback already passed;
- the publish-from-saved plan uses the same delivery-intent decision and has
  Codex/tool approval;
- the target branch and object IDs are explicit;
- `DATALENS_MCP_LIVE_ALLOW_PUBLISH=1` is set only for the publish process;
- deployment report will include published readback evidence.

## Runner

```bash
python3 scripts/run_live_checks.py
```

`run_live_checks.py` is also opt-in. It skips unless
`DATALENS_MCP_RUN_LIVE_TESTS=1` is present. When enabled, it runs the read-only
smoke first and then the live unittest group.
