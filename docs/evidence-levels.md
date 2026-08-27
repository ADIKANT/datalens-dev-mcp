# Evidence levels

Evidence claims are typed and ordered:

1. `source_static` — source, schema, policy, or deterministic static validation.
2. `installed_static` — static evidence from the installed server build.
3. `live_read_only_api` — fresh evidence from a read-only provider call.
4. `contract_runtime` — controlled non-browser runtime contract execution.
5. `save_readback` — fresh readback of the saved revision.
6. `publish_readback` — fresh readback of the published revision.
7. `browser_rendered` — revision-bound browser evidence when required.
8. `controlled_live_write` — authorized controlled-environment lifecycle proof.

A lower level cannot create a higher-level claim. Browser evidence is called only when the task policy requires it. Heavy evidence is stored once and returned as a resource URI, SHA-256, size, and synopsis. Reference retrieval returns at most three inline fragments with source identity, hash, authority, and stale advisory.

Task completion must state any missing level as a limitation. `live_verified` remains false unless the controlled canary actually completes.

`schema_static_fallback`, `saved_readback`, and `published_readback` are not proof levels. A dataset endpoint fallback is represented as `source_static` plus an explicit `fallback_kind`.
