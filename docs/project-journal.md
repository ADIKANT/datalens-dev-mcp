# Project Journal

Each autonomous task has a project-local journal under `.datalens-mcp/tasks/<task-id>/`. It contains the immutable contract, target/server identity, append-only hash-chained events, materialized state, compact checkpoint, receipts, evidence, snapshots, and a process lease.

Resume is allowed only when contract hash, project root, target identity, server build, branch, and source tree still match. Successful transition idempotency keys prevent a completed save from running again after restart. A transport failure during a write moves the workflow to reconciliation instead of repeating the write.

`checkpoint.md` is bounded operator context. `compact-context.json` separates stable policy/contract/binding/checkpoint identity from the last state change, active blocker or hypothesis, and next transition. Identical polls and timestamp-only changes do not churn the stable context hash.

The journal is local runtime state and must not be committed. Exact receipts expose resource URIs and SHA-256 identities without returning full object payloads to the model.
