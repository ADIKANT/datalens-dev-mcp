# Typed data validation

Data proof uses declarative assertion specifications and the curated read-only `getDatasetData` route. The server validates saved dataset and field identities, filters, parameters, ordering, paging, and row/cell/byte budgets before requesting data.

The route also supplies bounded planning context. `context_probe` selects the smallest relevant GUID set and derives observed field roles, date bounds, selector samples, null/zero/negative signals, and visualization constraints before the semantic plan is built. The resulting profile, query set, schema hash, observation time, and limitations are bound to the public plan. `assertion_probe` is always a separate fresh verification read; `diagnostic_probe` is used only to explain empty or inconsistent results.

Paging is deterministic only when the sort contract proves a total order, including a unique tie-breaker. The assertion engine supports typed null, uniqueness, range, set, date, aggregate, relationship, selector, formatting, and empty-result checks. It never executes model-written validation code.

Expected empty results are valid business outcomes. Unexpected empty results produce bounded diagnostics for filters, parameters, dates, field GUIDs, selector domain, physical availability, and saved/published branch alignment. Full rows remain in ignored local artifacts; MCP responses contain schema, counts, metrics, and small redacted examples.

If the experimental data endpoint is unavailable, the result is an explicit static-schema fallback with `live_data_verified=false`, never a successful live-data claim.

The endpoint has no revision or branch argument. A response therefore proves only the bounded rows observed through the current API route; it cannot by itself prove saved-versus-published parity. Positional rows are normalized against the exact schema from the same call. Complex values with an unproven wire format are preserved as raw typed values instead of being guessed.
