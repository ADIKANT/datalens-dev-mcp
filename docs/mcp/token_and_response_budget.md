# MCP Token And Response Budget

Startup and default read responses stay bounded. The standard `tools/list`
surface is the single normal Codex surface, and default reads return summaries,
short previews, hashes, counts, and artifact metadata instead of hydrated
payloads.

Budget rules:

- `tools/list` standard surface: at most 40 tools and under the tested JSON
  response budget. Tool schemas are generated through the cached runtime
  registry so repeated startup/list calls do not rebuild previous-version schemas.
- Project context is supplied as `project_context_ref.v1` by Project Memory
  Bank; DataLens does not duplicate startup-file reads in its responses.
- `dl_reference`: bounded inline response with `summary`, at most five `rules`,
  exact next standard tools, artifact paths for longer details, version, and
  date.
- `dl_read_object` and discovery helpers: summary by default; full or artifact
  modes must be explicit.
- Safe apply execution: inline status plus artifact metadata; raw envelopes are
  written once under `artifacts/safe_apply/`.
- SQL/performance diagnostics: compact findings inline; full evidence under
  `artifacts/sql_performance/`.

When a caller needs exact payloads, return artifact path, byte/character size,
and SHA-256 instead of expanding the MCP response.
