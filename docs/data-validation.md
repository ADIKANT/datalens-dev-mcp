# Typed data validation

Data proof uses declarative assertion specifications and the curated read-only `getDatasetData` route. The server validates saved dataset and field identities, filters, parameters, ordering, paging, and row/cell/byte budgets before requesting data.

Paging is deterministic only when the sort contract proves a total order, including a unique tie-breaker. The assertion engine supports typed null, uniqueness, range, set, date, aggregate, relationship, selector, formatting, and empty-result checks. It never executes model-written validation code.

Expected empty results are valid business outcomes. Unexpected empty results produce bounded diagnostics for filters, parameters, dates, field GUIDs, selector domain, physical availability, and saved/published branch alignment. Full rows remain in ignored local artifacts; MCP responses contain schema, counts, metrics, and small redacted examples.

If the experimental data endpoint is unavailable, the result is an explicit static-schema fallback with `live_data_verified=false`, never a successful live-data claim.
