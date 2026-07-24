# MCP Optimization Budget

Canonical budget rules now live in
`docs/mcp/token_and_response_budget.md`. This page remains as a short redirect
pointer for older references.

Startup and default read responses must stay bounded. The standard tool list
stays under the acceptance budget, and default reads return summaries or
artifact metadata instead of full hydrated payloads.

Budget rules:

- `tools/list` standard surface: exactly 39 tools and at most 25,000 UTF-8 JSON
  bytes.
- Project context is supplied as `project_context_ref.v1` by Project Memory
  Bank; DataLens does not duplicate startup-file reads in its responses.
- `dl_reference`: bounded inline response; oversized evidence spills to
  `artifacts/final_quality_program/02_semantic_authoring/`.
- `dl_read_object` and discovery helpers: summary by default; `full` or
  `artifact` is explicit.
- Safe apply execution: inline status plus artifact metadata; raw envelopes are
  written once under `artifacts/safe_apply/`.
- SQL/performance diagnostics: compact findings inline; full evidence under
  `artifacts/sql_performance/`.
- High-fanout selectors and large detail-table sources: push filters into SQL,
  dedupe to business grain before Editor/browser fetch, and return source
  budget metadata with physical rows, business rows, filter-pushdown status,
  and dedupe status. Missing or failing metadata blocks publish.

When a caller needs exact payloads, return artifact path, byte/character size,
and SHA-256 instead of expanding the MCP response.
