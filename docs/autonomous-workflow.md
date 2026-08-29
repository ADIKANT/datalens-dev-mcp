# Autonomous workflow

The default MCP surface owns a complete task rather than exposing every internal API operation. A task compiles current user intent into an immutable contract, resolves the target graph, binds route and style, plans data proof, validates a semantic change, saves, reads the saved state, publishes from that verified saved state, reads the published state, and verifies completion.

The public surface stays at nine tools or fewer. Start work with `dl_task_start`; use `dl_task_resume` after interruption; use `dl_task_status` for a bounded checkpoint; use `dl_evidence` for artifact-backed proof. Low-level legacy tools remain available only through the compatibility surface.

Browser and QL are explicit-intent capabilities. A browser-forbidden contract performs zero browser calls. QL is never selected as a fallback. Existing-object updates preserve technology, unknown fields, identity, and protected runtime unless the task explicitly requests a migration.

Every accepted user turn is classified as a new task, continuation, correction, scope restriction, or operation authorization. A material follow-up on the same task is installed as an immutable contract amendment with optimistic revision checks and an idempotent source-event key. Semantic-only changes preserve target and readback evidence; target/reference changes require fresh discovery; a post-save amendment preserves the saved receipts but invalidates any stale publish plan. A replacement goal never silently reopens a terminal task.

All URLs in the user-authored request are inventoried by role. External issue or documentation URLs are evidence, an explicitly labelled DataLens URL is the target, and a DataLens example/reference URL binds style separately. Ambient browser state is not promoted into the task contract. Scoped removal of a legend, field, header, prefix, row, or similar in-object content is an update; permission mutation requires an actual permission term plus an action, so ordinary words such as Russian `справа` or `доступно` do not trigger destructive handling.

Failures follow one recovery transition. Safe reads may retry within a budget. An ambiguous write is reconciled by readback and is never replayed. Three failed corrective attempts in one family stop at architecture review.

Completion requires evidence at the claimed level. A green local check is not a saved or published readback, and contract runtime proof is not browser-rendered proof.

## Dataset context before planning

When the target graph contains a dataset, the server uses the experimental read-only `getDatasetData` route in three bounded internal modes. `context_probe` runs before plan materialization and derives a field catalog, observed date bounds, candidate measure/dimension/selector roles, sampled domains, and explicit sample limitations. Its profile and query-set hashes are bound into the immutable public plan. `assertion_probe` performs a fresh typed read during verification. `diagnostic_probe` distinguishes an expected empty result from filters, parameters, date windows, field/schema mismatches, and provider unavailability.

Rows are positional and are interpreted only with the exact response schema from the same call. Requests use field GUIDs, bounded row/cell/byte budgets, and deterministic paging only when a total order is proven. Raw rows stay in ignored local artifacts; primary MCP responses contain hashes, counts, limitations, and redacted summaries. Because the route has no revision or branch parameter, it proves only the rows observed through that route. If it is unavailable, claims degrade to `source_static` with an explicit fallback kind and never become a successful live-data claim.

## Public behavior regression

Two different regression assets are intentionally retained:

- `tests/regression/policy_matrix/` is a static synthetic matrix for schemas, invariants, route policy, privacy, and failure vocabulary.
- `tests/regression/behavior_traces/` contains 40 sanitized behavior families and 80 executable variants. Every variant enters through public `tools/call` on `JsonRpcServer` under `autonomous-v2`; only the external DataLens transport, browser, clock/wait, filesystem, and build-identity boundaries may be mocked.

## Installed public proof

The final controlled canary starts the installed package through stdio and uses
only the eight public tools. It proves save, process restart, resume, publish,
saved/published readback, typed dataset evidence, forbidden-browser zero calls,
and stale-plan zero writes against one frozen source tree. The receipt contract
and operator command are documented in
[`public-autonomy-canary.md`](public-autonomy-canary.md).

The external session archive is used only by the offline builder. Packaged traces contain stable placeholders and aggregate provenance hashes, never raw transcripts, private paths, object IDs, URLs, tokens, or business values. Run `scripts/validate_behavior_trace_corpus.py` for the privacy/schema gate and `scripts/run_public_autonomy_acceptance.py` for the public-only E2E receipt.
