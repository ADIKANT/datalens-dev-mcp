# Contributing

Thank you for helping improve `datalens-dev-mcp`. The project welcomes focused
bug fixes, tests, documentation, and small feature proposals that preserve its
local stdio and guarded-write safety model.

## Before you start

- Search existing issues and pull requests before opening a duplicate.
- Open a feature request before implementing a new MCP tool, write route, or
  breaking response-contract change.
- Do not use a live customer workbook as a test fixture. Examples and fixtures
  must be synthetic and contain no private identifiers or credentials.
- Keep the server local and stdio-based. A hosted service or remote
  distribution mode is outside the current project scope.

## Development setup

Python 3.11 or newer is required.

```bash
git clone https://github.com/ADIKANT/datalens-dev-mcp.git
cd datalens-dev-mcp
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -e '.[dev]'
```

Run the offline acceptance gate before submitting changes:

```bash
.venv/bin/python scripts/run_offline_acceptance.py
```

When the public-release checker is present, run it as well:

```bash
.venv/bin/python scripts/check_public_release.py
```

No live DataLens call is required for ordinary contribution validation.

## Change rules

Route-policy changes must update the relevant configuration, schemas,
validators, examples, documentation, and tests together. Keep these safety
properties intact:

- read-only DataLens behavior by default;
- explicit local enablement for writes;
- fresh read and revision preservation before a mutation;
- saved readback before any permitted publish;
- no guessed identifiers, blind writes, or implicit QL fallback.

Runtime behavior belongs in MCP-native code, compact configuration, schemas,
templates, examples, and tests. Do not add raw books, courses, copied chapters,
full documentation mirrors, scraping output, or long source extracts.

## Third-party material and provenance

Only submit work that you have the right to contribute. By opening a pull
request, you agree that your contribution may be distributed under the Apache
License 2.0 and that you have authority to provide it under those terms.

Small adaptations from compatible public sources require a source URL,
copyright notice, license identifier, and a clear description of the changes.
Updates to Yandex Cloud documentation-derived registries must retain per-record
provenance and the attribution described in `THIRD_PARTY_NOTICES.md`. Do not
label OpenAPI-derived interface data as CC BY 4.0 unless the upstream source
itself adds an applicable license grant.

## Pull requests

Keep each pull request reviewable and include:

- a concise problem statement and solution summary;
- tests for changed behavior;
- the exact validation commands and results;
- documentation for user-visible changes;
- confirmation that fixtures are synthetic and the diff contains no secrets,
  private IDs, local paths, customer data, or source-material extracts.

Maintainers may ask for a smaller change or a design issue before accepting a
large refactor. Release versioning and publication are maintainer actions.
