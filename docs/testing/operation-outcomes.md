# Operation outcomes and bounded reads (1.2.8)

Historical release evidence; current cleanup behavior is described below. Current 429 guidance is in [rate-limit recovery](../../skills/datalens-inspect/references/direct-reads.md#rate-limits).

## Changed owners

- The SDK adapter distinguishes preparation from send using the owned client's request hook. Injected clients without dispatch observation retain the conservative build/execute boundary. Durable receipts are still written before SDK entry, so a process crash in that gap remains unknown rather than permitting replay.
- Before create dispatch the existing receipt retains destination, type/name/client reference, significant bindings, content fields and a content hash. This is diagnostic evidence, not provider idempotency or global name/hash deduplication.
- Per-item and overall errors distinguish confirmed pre-dispatch failure, explicit single-request provider rejection, and unknown or composite effects. Cleanup no longer treats an arbitrary HTTP response as proof of rejection. No mutation retry or revision guard was added or removed.
- Inventory requires the correct endpoint container and valid identities. Malformed pages retain prior valid entries, numeric continuation and an explicit failure. Relation tokens retain their separate contract.
- The direct HTTP transport reads at most the configured byte limit plus one detection byte, closes success/error responses and never emits error bodies. Safe reads share a deadline, bounded exponential backoff and Retry-After; local OS errors and writes do not get transient retries. Socket timeout and checks between chunks bound waits; this is not an interruptible DNS resolver.
- Full state comparisons remain server-side. Default diffs cap paths and represent large values by size/hash. Named dashboard global-parameter deletion uses the existing typed mutation service, exact revision and absence readback.

## Bounds and evidence

The default direct HTTP response limit is 32 MiB, configurable up to 256 MiB. An addressed retained real Dataset receipt was approximately 34 KiB of readback JSON; previously observed dashboard request payloads exceeded 200 KiB. The default leaves substantial headroom above that evidence. Current live response sizes still require measurement; this is not a claim that every provider object fits. A required full object over the limit fails explicitly and needs a reviewed larger limit. Smaller inventory pages and bounded data queries are the supported alternatives where applicable; a projection does not avoid fetching the underlying object.

The default safe-read budget is 60 seconds, configurable up to 300 seconds; individual request timeouts remain separately bounded. Retry delays cap at five seconds, and a longer provider Retry-After returns the error instead of retrying early.

Existing offline tests cover SDK preparation failures, local build rejection, post-send loss, provider rejection, strict empty/invalid inventory, bounded/closed HTTP responses, Retry-After, receipt retention, revision/absence checks and compact source diffs. These tests do not establish live API or crash behavior.

## Live and parallelism boundary

The connected runtime's auth probe and one deliberate recovery both ended in credential-helper timeout. Helper launch/version and IAM reachability succeeded, which does not establish the timeout cause or a need for interactive login. No repeated helper loop, account switch or credentials change was performed. Historical unknown receipts remain intact; absent inventory is not evidence that a create was unapplied.

A successful small live read benchmark was unavailable under this auth boundary. Stdio dispatch therefore remains sequential: there is no measured benefit justifying a concurrent dispatcher or shared-client concurrency change. After successful authentication, measure independent scoped reads and retain each result before considering concurrency. No live mutation, network fault injection, duplicate creation or rendered canary is claimed by this release note. Post-install native identity, authorized cleanup and Editor save/publish/render/restore remain separate acceptance obligations.


## Bounded cleanup and recovery (1.2.20)

Cleanup preview/apply share an operation deadline (default 120 seconds, maximum 180) and an actual provider-dispatch limit (default 200, maximum 1,000), including internal SDK requests and credential refresh. Progress reports the active phase, elapsed time, provider reads/effects and completed/known remaining preview reads. The remaining count is a lower bound until all dependencies have been discovered. A blocked preview cannot authorize deletion; inspect its exact remaining reads and typed issues before choosing a smaller authorized scope or a fresh preview. Successful evidence is reused only within that operation, never as a global graph cache.

Deadline/cancellation checks stop new dispatch. A blocking socket phase may take its remaining timeout (capped at 30 seconds) to unwind; OS DNS is not interruptible. The stdio control plane handles ping, server identity, cancellation and receipt reads independently while one domain worker exclusively owns the SDK. Other domain calls receive a busy response without dispatch. Cancellation after a dispatched write never means that no change occurred.

Preview returns the cleanup operation ID before apply. Apply durably binds it to the exact ordered target set, preview fingerprint and authentication/provider scope before dispatch. Fresh graph/revision checks and consumer-before-dependency deletion remain mandatory. A separate process lease prevents overlapping cleanup writers without blocking receipt reads. Confirmed absence comes from an exact object read, never inventory or a relations error.

Repeated apply for the same admitted operation reconciles without replaying deletes. Unknown effects also block a new operation ID over the same target. Read the receipt with `dl_operation_get`, then use read-only `dl_operation_reconcile`; a still-readable object does not disprove an in-flight effect. After known outcomes, a fresh preview may authorize remaining unattempted targets. `preview_changed` states only that this operation dispatched no new delete, not that an older unknown operation had no effect. Typed provider diagnostics survive cleanup and MCP envelopes.

Offline checks and local renderer replays do not establish native concurrent-host responsiveness, provider crash recovery, publication, selector interaction or live ChartKit rendering. Those require a separately authorized run-owned canary and the installed native build.

### Read barrier diagnostics (1.2.21)

A read can already be dispatched when its deadline or cancellation barrier is reached. Its error retains `dispatch_state=dispatched` through cleanup relation conversion, without inventing a mutation outcome. If response headers arrived, the body-read error retains the observed HTTP status, `response_received=true`, `stage=response_read` and allowlisted correlation IDs. A dispatched write interrupted at the same boundary remains unknown.

When a transport timeout returns after the operation deadline, it is classified as `operation_budget_exhausted`, not a generic provider failure suggesting another read. This diagnostic correction does not make synchronous socket phases or OS DNS immediately interruptible; strict wall-clock acceptance remains separate from preventing further dispatch.


### Cleanup response deadline (1.2.22)

The native stdio boundary now reserves up to 250 ms (at most 10% of the requested
budget) for response encoding and delivery. One bounded timer can return an
incomplete result if a synchronous provider call is still unwinding. It does not
start another domain worker, release the active-operation slot, interrupt DNS or
replay the call. Late completion produces no second JSON-RPC response. Host
delivery and OS scheduling remain outside the server's timing guarantee.

Expiry and provider admission share a lock. Progress includes the active phase,
admitted read/effect counts and a snapshot of completed/known remaining preview
reads. Incomplete results never authorize deletion. A timed-out apply retains
its operation ID and an unknown outcome: zero new effects do not disprove an
older effect under that ID. Read its durable receipt through the control plane;
reconcile read-only after the worker finishes. Receipt admission and outcome
updates remain owned by the existing cleanup service/store.

Existing offline checks cover response-before-unwind, late-response suppression,
cancellation and dispatch barriers, and unchanged input rejection. A direct
source/provider read is a separate evidence level; native host acceptance still
requires loading this build and repeating the affected scoped scenario.
