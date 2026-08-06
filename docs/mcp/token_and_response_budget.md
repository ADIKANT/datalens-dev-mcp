# MCP Token And Response Budget

Startup and default read responses stay bounded. The standard `tools/list`
surface is the single normal client surface, and default reads return summaries,
short previews, hashes, counts, and artifact metadata instead of hydrated
payloads.

Budget rules:

- `tools/list` standard surface: exactly 39 tools and at most 25,000 UTF-8
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
- `dl_generate_editor_bundle` and `dl_execute_safe_apply` are compact,
  artifact-backed execution tools. Their standard MCP surface does not hydrate
  full bundles, tabs, request envelopes, or readback bodies inline. The
  canonical sanitized response is written once and identified by path, size,
  character count, and SHA-256. `response_mode=full` is not part of these two
  tools' standard schemas.
- A `chart_specs` batch returns one bounded batch summary, at most 100
  per-widget status records with bundle paths and compiled hashes, one batch
  manifest path, and one compact browser-QA-plan reference. Complete bundles
  remain under their artifact paths and `full_bundles` is `artifact_only`.
- The compact `dl_execute_safe_apply` response reports execution state, counts,
  saved and published readback paths, blocking reasons, proof levels, and
  metrics. One executor call owns group save, saved readback, publish preflight,
  publish from saved state, and published readback; clients must not expand
  each nested stage into a separate inline transcript.
- Safe-apply/publish planners, guarded RPC, and project workflow tools: `summary`
  by default with a typical 15K inline ceiling. The canonical sanitized result
  is stored once with its SHA-256; `full` remains explicit and compatible.
- Editor validation: stable `corpus_reference_set` by default. Full corpus
  reference rows require `include_references=true`; repeated payloads reuse the
  validation result for the same rule-resource version.
- Repeated dashboard snapshots may reuse hydrated artifacts only after fresh
  dashboard reads, bounded complete workbook-inventory pagination, a fresh
  canonical relations match, target-graph revision checks, and artifact hash
  verification. Unrelated workbook revisions refresh the inventory artifact
  without forcing target-graph hydration.
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

For a normal strict Editor dashboard, the token-bounded path is:

```text
one scoped baseline
  -> one dl_generate_editor_bundle call with strict_dashboard + chart_specs
  -> local validation and one safe-apply plan
  -> one dl_execute_safe_apply
  -> one generated browser QA pass
```

The browser QA artifact fixes the runtime work to one navigation, one batched
read-only evaluation across `720 x 900`, `1200 x 900`, and `1440 x 900`, and one batched
screenshot operation. Its call budget is three. Do not replace it with
per-widget DOM exploration, mutation, reload loops, or repeated screenshots.
If the pass fails, use its assertion results and artifacts to make a scoped
change, then generate a new hash-bound plan.

The serialized projection stays within a valid `inline_char_budget`. If the
summary itself is oversized, the inline value becomes a deterministic compact
record with item count, hash, bounded preview, and the full-response artifact
pointer. A budget too small to carry that minimum pointer contract is rejected
instead of returning an oversized response.

For `dl_read_object`, the supported minimum is 800 characters. The projection,
method/object envelope, branch, and full or compact read-contract metadata all
share that one budget; no metadata is appended after the size check.
