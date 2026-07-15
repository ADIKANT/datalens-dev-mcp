# Testing

| Category | Command | When To Run | Requires | Coverage |
| --- | --- | --- | --- | --- |
| Quick | `python3 scripts/run_quick_checks.py` | Before/after local edits and before final acceptance | Committed repo only | cleanup idempotence, Python compile/style, schema and runtime resource manifest checks, JS syntax and `Editor.wrapFn`, docs/API policy when cheap, MCP stdio smoke, high-signal unit tests |
| Standard | `python3 scripts/run_offline_acceptance.py` | Before claiming the repo is ready | Committed repo only | quick static/smoke gates, all unit tests, offline integration tests, public-release surface, repo-size/generated-artifact policy, sensitive-artifact scan |
| Full | `python3 scripts/run_acceptance_profile.py --profile full` | Release, wheel, or golden runtime fixture runs | Committed repo only by default; optional live proof needs separate disposable approval | standard profile, wheel build and installed-wheel smoke, golden runtime gallery fixtures, project manifest fixtures, optional controlled live proof |
| Live Read-Only | `python3 scripts/run_live_checks.py` with `DATALENS_MCP_RUN_LIVE_TESTS=1` | Optional operator verification against disposable or approved DataLens targets | local credentials in env only | auth probe, workbook list/read, optional object read, local planning without writes |
| Live Save-Only Disposable | Approved safe-apply flow with `DATALENS_MCP_ENABLE_WRITES=1` and a disposable target | Only after reviewing an approved safe-apply plan | disposable workbook/object, Codex/tool approval, fresh read, save mode | guarded save, revision preservation, saved readback, deployment report |
| Gated Publish From Saved | After saved readback for known live implementation/fix/enhance targets with no draft/no-publish instruction | Required continuation of approved delivery intent | explicit write/save/publish gates, Codex/tool approval, saved readback artifact | publish-from-saved plan and published readback |

## Quick

```bash
python3 scripts/run_quick_checks.py
```

Quick checks are intentionally idempotent. The first step runs
`scripts/clean_local_runtime_artifacts.py`, which removes only generated
garbage such as `.DS_Store`, `__pycache__`, `*.pyc`, `.pytest_cache`, and
`.ruff_cache`.

## Standard

```bash
python3 scripts/run_offline_acceptance.py
```

Purpose:

- Runs quick static, docs/API, manifest, and stdio gates without duplicating the
  quick focused unit subset.
- Runs all unit tests.
- Runs offline integration tests.
- Runs public-release, repo-size/generated-artifact, and sensitive-artifact
  gates.
- Compares visible `git status` before and after the profile and fails if the
  profile introduces non-ignored tree changes.
- Writes timing summaries and command logs under ignored
  `artifacts/validation_profiles/standard/<run_id>/`.
- Does not require external repositories, local runtime caches, raw material
  manifests, live credentials, or live DataLens writes.

## Full

```bash
python3 scripts/run_acceptance_profile.py --profile full
```

Purpose:

- Runs the standard profile.
- Builds a wheel under ignored validation artifacts and runs installed-wheel
  portable smoke from a temporary directory.
- Checks golden runtime gallery contracts and project manifest fixtures.
- Skips controlled live proof unless `DATALENS_MCP_RUN_CONTROLLED_LIVE_PROOF=1`,
  `DATALENS_MCP_APPROVED_CONTROLLED_LIVE_WRITES=1`,
  `DATALENS_MCP_TEST_WORKBOOK_ID`, and
  `DATALENS_MCP_CONTROLLED_LIVE_APPROVAL_NOTE` are all supplied.

All validation profiles write compact JSON output with per-step `duration_ms`,
log artifact paths, byte sizes, and SHA-256 hashes. Heavy command output,
readback replay details, wheel artifacts, and optional live evidence stay in
ignored artifact paths, not inline chat.

## Offline Compatibility

`scripts/run_quick_checks.py` and `scripts/run_offline_acceptance.py` are stable
compatibility wrappers around `scripts/run_acceptance_profile.py --profile
quick` and `--profile standard`.

## Live

```bash
DATALENS_MCP_RUN_LIVE_TESTS=1 \
DATALENS_ORG_ID=<ORG_ID> \
DATALENS_IAM_TOKEN=<IAM_TOKEN> \
python3 scripts/run_live_checks.py
```

Live checks are opt-in and start with `scripts/live_smoke_readonly.py`. The
read-only smoke never writes or publishes. Save checks require an approved
safe-apply plan, `DATALENS_MCP_ENABLE_WRITES=1`, a disposable target, fresh
read/revision preservation, save mode, and readback. Read-only checks exclude
publish; approved implementation/fix/enhance delivery uses the
publish-from-saved state after saved readback.

## Validation Policy

Keep checks that prevent real runtime failures:

- route policy
- template syntax and `Editor.wrapFn`/`Editor.generateHtml` contract
- sensitive credential leakage
- safe write gates
- payload schemas
- object relation preservation
- requirements persistence
- MCP stdio contract
- minimal readback defaults and justification

Default readback is `minimal`; use `full` only for high-risk saved changes and
use `none` only with an explicit justification.

Avoid duplicate tests when config, schemas, or templates already enforce the
same static rule, unless the duplicate catches runtime/API integration behavior.
