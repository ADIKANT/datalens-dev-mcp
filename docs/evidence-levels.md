# Evidence levels

Evidence claims are typed and ordered:

1. `source_static` — source, schema, policy, or deterministic static validation.
2. `contract_runtime` — controlled non-browser runtime contract execution.
3. `saved_readback` — fresh readback of the saved revision.
4. `published_readback` — fresh readback of the published revision.
5. `browser_rendered` — revision-bound browser evidence when required.
6. `controlled_live_write` — authorized controlled-environment lifecycle proof.

A lower level cannot create a higher-level claim. Browser evidence is called only when the task policy requires it. Heavy evidence is stored once and returned as a resource URI, SHA-256, size, and synopsis. Reference retrieval returns at most three inline fragments with source identity, hash, authority, and stale advisory.

Task completion must state any missing level as a limitation. `live_verified` remains false unless the controlled canary actually completes.
