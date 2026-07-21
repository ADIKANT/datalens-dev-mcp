# MCP Token And Response Budget

Startup and default read responses stay bounded. The standard `tools/list`
surface is the single normal client surface, and default reads return summaries,
short previews, hashes, counts, and artifact metadata instead of hydrated
payloads.

Budget rules:

- `tools/list` standard surface: exactly 38 tools and at most 25,000 UTF-8
  JSON bytes. Tool schemas omit descriptions only for self-evident identifiers
  and bounded knobs; safety-critical payload, configuration, write/delete,
  readback, and current/proposed-state guidance remains inline. Schemas are
  generated through the cached runtime registry so repeated startup/list calls
  do not rebuild previous-version schemas.
- Project context is supplied as `project_context_ref.v1` by Project Memory
  Bank; DataLens does not duplicate startup-file reads in its responses.
- `dl_reference`: bounded inline response with `summary`, at most five `rules`,
  exact next standard tools, artifact paths for longer details, version, and
  date.
- `dl_read_object` and discovery helpers: summary by default; full or artifact
  modes must be explicit.
- Safe apply execution: inline status plus artifact metadata; raw envelopes are
  written once under `artifacts/safe_apply/`. Nested save/publish delivery
  summaries do not duplicate full action payloads, command output, or publish
  plans already present at the top level or in artifacts.
- Safe-apply/publish planners, guarded RPC, and project workflow tools: `summary`
  by default with a typical 15K inline ceiling. The canonical sanitized result
  is stored once with its SHA-256; `full` remains explicit and compatible.
- Editor validation: stable `corpus_reference_set` by default. Full corpus
  reference rows require `include_references=true`; repeated payloads reuse the
  validation result for the same rule-resource version.
- Repeated dashboard snapshots may reuse hydrated artifacts only after fresh
  dashboard reads, a revision-complete workbook inventory match, and artifact
  hash verification.
- SQL/performance diagnostics: compact findings inline; full evidence under
  `artifacts/sql_performance/`.

The server applies lazy discovery at the public-API boundary:
`dl_list_api_methods` returns the curated command inventory,
and `dl_get_api_method_schema` expands only the selected contract. Execution
continues through the standard read or object-lifecycle tools. Common dashboard
workflows remain first-class tools because their target locks, revision checks,
save/readback, publish, and evidence contracts are materially stronger than a
generic RPC gateway. This keeps ordinary authoring one-step discoverable
without exposing unguarded mutation.

When a caller needs exact payloads, return artifact path, byte/character size,
and SHA-256 instead of expanding the MCP response.

The serialized projection stays within a valid `inline_char_budget`. If the
summary itself is oversized, the inline value becomes a deterministic compact
record with item count, hash, bounded preview, and the full-response artifact
pointer. A budget too small to carry that minimum pointer contract is rejected
instead of returning an oversized response.

For `dl_read_object`, the supported minimum is 800 characters. The projection,
method/object envelope, branch, and full or compact read-contract metadata all
share that one budget; no metadata is appended after the size check.
