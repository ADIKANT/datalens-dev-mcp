# Stable releases

`pyproject.toml` owns the package version. Choose a free `MAJOR.MINOR.PATCH`
above all prior releases (including local versions under Python version ordering).
A release preparation command copies that version to the static runtime and plugin
manifest; neither installation nor MCP startup changes source or receipts:

```sh
python scripts/release_version.py --sync --previous PREVIOUS_VERSION --check-git
```

Fetch all tags before validation. `--existing-tag` accepts explicit inventory
entries for disconnected checks. Without `--sync`, validation is read-only.
`--tag vX.Y.Z --check-git` additionally validates an existing release tag against
HEAD; it never permits reusing a tag pointing to another commit. Create release
tags only on the reviewed merged commit. CI checks version mirrors and the fetched
tag inventory, archive contents/metadata and an isolated installed stdio process.

The first stable release after `1.1.0+codex.20260910071145` is `1.1.1`.
This release retains SDK `0.9.0`; SDK migration is a separate change.
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
