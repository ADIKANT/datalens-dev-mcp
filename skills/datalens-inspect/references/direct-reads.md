# Direct reads

- Use `dl_auth_check` only for a harmless access probe. It does not inspect a workbook graph.
- Use `dl_workbooks_list` or `dl_workbook_entries` for inventory. These tools traverse numeric pages internally up to `max_pages`; a returned `next_page_token` means the result is still partial, not a token accepted by these tools. Use a sufficient page bound for complete inventory. A repeated-token result is a provider/contract diagnostic, not a reason to keep raising the bound. Entry pages contain at most 200 objects. `type` retains the provider scope; `object_type` gives the typed read route and `subtype` preserves the actual renderer. Unknown subtypes stay explicit. To inspect a workbook itself, use `dl_object_get(object_type="workbook", object_id=...)`: its name, description and revision belong to the workbook object. An entry listing describes its contents; even a complete empty listing does not verify workbook metadata or its current revision.
- Use `dl_object_get` with an exact object type and ID. Set `branch` explicitly when saved versus published state matters, and use `revision_id` only when the user supplied or a prior read returned it. Use `view="summary"` for identity/version/completeness, or `view="projection"` with RFC 6901 `fields` such as `["/dataset/description"]` for exact paths. A non-full result has `full_state=false` and supplies `full_read`; follow that exact tool address before replacement. Never pass summary/projection output to a full-object update. `view="full"` remains backward compatible.
- Use `dl_object_relations` for direct dependencies. Continue with the returned opaque `page_token`; copy it exactly and never construct one. Do not substitute a workbook-wide scan unless the requested evidence actually requires complete inventory.
- Use `dl_dashboard_snapshot` for a dashboard plus its direct relation dependencies. Continue a bounded traversal with the returned opaque `continuation` token; copy it exactly into `continuation` and keep the same scope. `complete` means traversal completed for that scope. If the provider has no snapshot token, `graph_consistency` remains unverified and traversal completeness is not point-in-time consistency. `target` is the object being evaluated; an optional `reference` is style evidence and must never replace the target or donate its data identifiers.

Reuse an already sufficient addressed read while its source and scope remain current. Do not follow a projection with a broad snapshot unless the task needs more evidence. Full object reads return provider payloads in `structuredContent`; text carries a short identity summary. `dl_object_diff` reads only its target and returns changed paths/values; request `include_proposed=true` only for the full merged snapshot. A metadata edit does not require a dashboard snapshot. Summaries and projections stay compact and identify their view, completeness and full-read address. Do not write audit artifacts into the working project; if a large payload must be retained, the user or calling host chooses an explicit output path.

Dataset query success is data evidence, not proof of a saved or published chart. Editor source/static checks are distinct from browser runtime behavior. Report unsupported scope, incomplete relations, tenant denial, and branch uncertainty as limitations rather than inventing evidence.

## Retain full state without dumping it

Prefer the tool's summary/projection views for inspection. When a full snapshot is needed for preservation, retain `structuredContent` in the caller's private state or authorized output file, then select model-facing fields **before** calling `text()` or serializing a wrapper. Emit identity/revision, selected bindings, completeness and errors once; do not print both `content` and `structuredContent`. Printing a full payload and truncating afterward loses evidence and context. Keep full reads and saved/published readback available for safe writes.

In a host with `store`/`text`, for a successful full object read already held as `result`:

```javascript
const value = result.structuredContent;
store("targetFullState", value);
text({ok: value.ok, identity: value.identity, full_state: value.full_state});
```

Select the actual fields needed for the next decision separately; return a failed tool's compact error rather than treating missing state as an empty object. Private state is not durable backup across a process restart.

Inventory validates its endpoint-specific container and item identities. A malformed page returns `ok=false`, `complete=false`, prior valid objects and numeric `failed_page`/`next_page`; it cannot prove emptiness or absence. Keep numeric workbook continuation separate from opaque relation tokens. Reuse a complete current inventory across independent reads; refresh only for changed scope/revisions, stale evidence, or the relevant mutation preflight.

The direct HTTP reader bounds response bytes and read time, closes responses, and returns explicit size/JSON failures without login HTML or silent truncation. Use smaller inventory pages or a bounded Dataset query when possible. For a required full object exceeding the configured limit, stop replacement and review a larger `DATALENS_MAX_RESPONSE_BYTES` limit (default 32 MiB, maximum 256 MiB). Projections are formed after a full provider read and cannot bypass a transport limit. `DATALENS_READ_BUDGET_SEC` bounds safe-read attempts (default 60 seconds); only transient read errors get bounded backoff/Retry-After. Writes are never retried by this path.

`dl_object_diff` compares the complete target locally and returns up to 50 paths; large values are represented by byte counts and hashes. `changed_field_count` and `diff_complete` describe coverage. Request `include_proposed=true` only when full local state is actually needed, and select model-facing evidence before emitting it. Server writes still compare and verify the complete state.
