# Stable releases

`pyproject.toml` owns the package version. Choose a free `MAJOR.MINOR.PATCH`
above all prior releases (including local versions under Python version ordering).
A release preparation command copies that version to the static runtime and plugin
manifest; neither installation nor MCP startup changes source or receipts:

```sh
python scripts/release_version.py --sync --previous PREVIOUS_VERSION --check-git
```

Fetch all tags before validation. The initial legacy version is always a lower
bound, even before the first stable tag exists. CI uses `--allow-tagged-head`
to inspect an unchanged released commit; this mode cannot be used with `--sync`. `--existing-tag` accepts explicit inventory
entries for disconnected checks. Without `--sync`, validation is read-only.
`--tag vX.Y.Z --check-git` additionally validates an existing release tag against
HEAD; it never permits reusing a tag pointing to another commit. Create release
tags only on the reviewed merged commit. CI checks version mirrors and the fetched
tag inventory, archive contents/metadata and an isolated installed stdio process.

The first stable release after `1.1.0+codex.20260910071145` is `1.1.1`.
That historical release retained SDK `0.9.0`; current dependency versions are owned by `pyproject.toml`.
The content digest, capability revision and process instance identify the build
independently of the release version. Unknown source provenance stays null.

For an existing selected installation, retain the previous verified wheel before
installing the new wheel and refreshing the same plugin source through the host's
supported reinstall command. Use the stable manifest version; do not run a
cachebuster that appends a timestamp. Preserve the existing launcher, credentials,
configuration, receipts and other plugins. Reconnect only the DataLens MCP and
read `dl_server_info` before calling a new wheel active. If scoped reconnect is
unavailable, report the remaining user action. Roll back only this package/plugin
to its retained artifact; neither direction clears receipts or repeats effects.

Evidence levels remain distinct: offline tests, installed stdio, native host,
provider read, authorized write and browser rendering. A version change alone
proves none of the latter levels.

## Exact-source delivery

Complete feature-branch commit/push, PR checks and required review before merging main. Wait for fetch/merge commands to finish with exit code 0; a returned process/session handle is not completion. Verify the intended merge SHA belongs to fetched `origin/main`, then build from a clean checkout of that exact SHA. Do not build or install while a dependent Git command is running. Record source SHA → archive SHA256 → installed package/content digest and plugin assets. Preserve a delivered merge SHA if main later advances with unrelated work; do not restart delivery indefinitely. Unknown native `source_commit` remains null.

Refresh the selected existing runtime and plugin from that source; do not add a second MCP registration. Verify site-packages import outside the checkout with no `PYTHONPATH=src`, installed stdio/closed schemas and authorized read probes. After completing all local setup, request one full host restart if required, retain a private RESUME and wait for the user's return before native acceptance.

Use the [R1–R3 acceptance card](live_test_plan.md) for relevant release changes. Existing CI/offline checks remain required; neither their pass counts nor installed smoke substitute for native/provider/rendered evidence.
