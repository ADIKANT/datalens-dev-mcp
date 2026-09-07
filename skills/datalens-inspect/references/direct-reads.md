# Direct reads

- Use `dl_auth_check` only for a harmless access probe. It does not inspect a workbook graph.
- Use `dl_workbooks_list` or `dl_workbook_entries` for inventory. Continue while `next_page_token` is present; if `complete` is false, call the result partial.
- Use `dl_object_get` with an exact object type and ID. Set `branch` explicitly when saved versus published state matters, and use `revision_id` only when the user supplied or a prior read returned it.
- Use `dl_object_relations` for direct dependencies. Do not substitute a workbook-wide scan unless the requested evidence actually requires complete inventory.
- Use `dl_dashboard_snapshot` for a dashboard plus its direct relation dependencies. `target` is the object being evaluated; an optional `reference` is style evidence and must never replace the target or donate its data identifiers.

Object reads return provider payloads because later narrow updates need exact shape. Summaries and lists stay compact. Do not write audit artifacts into the working project; if a large payload must be retained, the user or calling host chooses an explicit output path.

Dataset query success is data evidence, not proof of a saved or published chart. Editor source/static checks are distinct from browser runtime behavior. Report unsupported scope, incomplete relations, tenant denial, and branch uncertainty as limitations rather than inventing evidence.
