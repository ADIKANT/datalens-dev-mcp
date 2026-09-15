# Operation outcomes and bounded reads (1.2.8)

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
