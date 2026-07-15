# Optional Live Test Plan

Source trace: official DataLens API catalog, safe-apply policy, and current MCP
tools. All targets must be explicitly supplied disposable objects.

See also `docs/live_testing_local.md`.

## Environment

- `DATALENS_MCP_RUN_LIVE_TESTS=1`
- `DATALENS_ORG_ID=<ORG_ID>`
- `DATALENS_IAM_TOKEN=<IAM_TOKEN>`
- `DATALENS_MCP_LIVE_WORKBOOK_ID=<DISPOSABLE_WORKBOOK_ID>` for optional workbook reads.
- `DATALENS_MCP_ENABLE_WRITES=1` only for approved disposable save steps.
- `DATALENS_MCP_LIVE_ALLOW_SAVE=1` for manual disposable save confirmation.
- `DATALENS_MCP_LIVE_ALLOW_PUBLISH=1` only for an approved publish-from-saved
  plan under the delivery-intent state machine.

## Sequence

1. Run `python3 scripts/live_smoke_readonly.py`.
2. Run `dl_probe_auth`.
3. Read disposable workbook entries with `dl_get_workbook_entries`.
4. Read connection and dataset metadata with `dl_get_connection` and `dl_get_dataset`.
5. Build Wizard-first standard chart and registered capability-gap Editor create
   plans without execution.
6. Approve save-only safe apply for disposable objects only.
7. Read saved dashboard/chart objects back.
8. Publish only after explicit user approval and saved readback evidence.
9. Clean up disposable objects manually through approved environment procedures.

Live execution in this run: `BLOCKED_LIVE_CREDENTIALS`.
