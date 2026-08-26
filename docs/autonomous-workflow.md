# Autonomous workflow

The default MCP surface owns a complete task rather than exposing every internal API operation. A task compiles current user intent into an immutable contract, resolves the target graph, binds route and style, plans data proof, validates a semantic change, saves, reads the saved state, publishes from that verified saved state, reads the published state, and verifies completion.

The public surface stays at nine tools or fewer. Start work with `dl_task_start`; use `dl_task_resume` after interruption; use `dl_task_status` for a bounded checkpoint; use `dl_evidence` for artifact-backed proof. Low-level legacy tools remain available only through the compatibility surface.

Browser and QL are explicit-intent capabilities. A browser-forbidden contract performs zero browser calls. QL is never selected as a fallback. Existing-object updates preserve technology, unknown fields, identity, and protected runtime unless the task explicitly requests a migration.

Failures follow one recovery transition. Safe reads may retry within a budget. An ambiguous write is reconciled by readback and is never replayed. Three failed corrective attempts in one family stop at architecture review.

Completion requires evidence at the claimed level. A green local check is not a saved or published readback, and contract runtime proof is not browser-rendered proof.
