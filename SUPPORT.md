# Support

`datalens-dev-mcp` is a community-maintained, independent project. Support is
provided on a best-effort basis and does not replace Yandex Cloud or Yandex
DataLens product support.

## Where to ask

- Reproducible server bugs: use the repository bug-report template.
- Feature proposals: use the feature-request template before implementing a
  new MCP tool or write route.
- Installation and usage questions: open a GitHub issue with the MCP client,
  operating system, Python version, server version, and sanitized logs.
- Vulnerabilities: follow `SECURITY.md`; never file them publicly.
- DataLens account, billing, availability, or product incidents: use the
  official Yandex Cloud support channel.

## Before opening an issue

Verify the installed version and run the offline gate when possible:

```bash
datalens-dev-mcp --version
python3 scripts/run_offline_acceptance.py
```

Include the exact command/configuration shape and the smallest synthetic
reproduction. Remove IAM tokens, authorization headers, org IDs, workbook and
object IDs, customer names, local usernames, absolute home paths, raw exports,
and private payloads. Replace each value with a clear placeholder instead of
partially masking a real credential.

There is no service-level agreement, private implementation consulting, or
guarantee that every undocumented DataLens API behavior will be supported.
