# Changelog

## 1.2.22

- Return incomplete cleanup responses within the reserved response deadline while the single SDK worker safely unwinds an in-flight call.
- Keep expiry atomic with dispatch admission, retain known read progress and receipt identity, and suppress late duplicate responses without replaying writes.
- Keep timed-out apply outcomes unknown even when no new effects were admitted, because an earlier effect under the same operation ID may remain unresolved.

## 1.2.21

- Preserve dispatched read evidence through budget/cancellation errors and cleanup relation envelopes, including known response status, phase and safe correlation IDs.
- Classify transport timeouts at an exhausted operation deadline as budget exhaustion without suggesting another read; keep dispatched write outcomes conservative.

## 1.2.20

- Bound cleanup provider calls and elapsed work, retain typed partial progress, and keep identity, ping, cancellation and receipt reads responsive while one worker owns the SDK.
- Persist cleanup admission and per-target outcomes before effects, reconcile without replay, and block overlapping unknown deletes across operation IDs and processes.
- Honor period-series comparison applicability and hidden legends; preserve real zeros and gaps with scoped empty-series policies and responsive signed-axis labels.
- Add an explicitly bound heatmap recipe with complete column labels, missing-cell semantics and narrow-widget scrolling; retain presentation precedence and current manual layout guidance.

## 1.2.19

- Align all domain skill references on presentation precedence, widget-owned KPI hints and evidence required before another write attempt.
- Scope inventory to set discovery/completeness, retain dependency previews for exact cleanup, and clarify recipe defaults and illustrative dates.

## 1.2.18

- Preserve allowlisted SDK transport failure types, request methods and phases through scoped reads and uncertain-write receipts, without exposing exception messages or URLs.
- Keep transport response evidence conservative and retain single-attempt writes and exact-target reconciliation.

## 1.2.17

- Classify HTTP 429 as rate limiting, preserve valid Retry-After and safe correlation metadata through tool responses and compact receipts, and keep uncertain write reconciliation ahead of read recovery.
- Surface SDK 429 responses before its Retry-After-unaware retry loop; retain the existing bounded raw-reader retries and add no write retries.
- Refresh obsolete contribution/live-acceptance commands, document exact-source release ordering, and retain one repeatable KPI, dependency and cleanup acceptance card.

## 1.2.16

- Read dashboard dependencies in the provider's outbound direction, expose an explicit dependency/consumer direction on compact relation reads, and describe direct pagination separately from revision consistency.
- Validate relation containers, identities and continuation before compaction. Preserve known elements on failures, stop malformed pages and cursor cycles, and keep snapshots and cleanup previews incomplete when evidence is incomplete.
- Reuse Dataset selector and parameter bindings for two-period KPI totals and trend. Query aggregate totals at their source grain, preserve missing values, and keep native All/Reset and meaningful zero/false values consistent across requests.

## 1.2.15

- Correct dependency and consumer directions in scoped cleanup, preserving protected roots, deletion order and fresh preview checks.

## 1.2.14

- Serialize generated Editor recipe configuration deterministically so saved artifacts pass source validation after JSON key reordering. Preserve rejection of actual source changes.
- Enable native selector range mode for interval defaults and reject an explicit conflicting single-date mode before writing.

## 1.2.13

- Resolve one normalized visual profile across recipes, direct Wizard creation and typed Dashboard composition. Keep current user/project choices above old reference styling and retain title alias compatibility.
- Apply widget title/hint ownership, actual measure labels, disabled axis grids, stable measure colors and native selector groups through the supported SDK. Keep business bindings separate from reusable renderers.
- Validate typed batches before their first write, compile Dashboard payloads locally and preflight Wizard fields without extra mutations. Preserve unrelated existing state and validate only changed Editor source fragments.
- Reuse the packaged KPI/period renderers with placement-owned headings and hints, controlled gridlines and explicit missing-value handling.

## 1.2.12

- Let explicit IAM refresh use the configured YC profile's external browser sign-in with a bounded two-minute wait. Keep automatic refresh noninteractive and provide an explicit browser-disabled option.
- Distinguish browser-enabled recovery from background timeouts, retain secret-free API verification and clarify authorized same-account SSO recovery without changing host permissions or replaying writes.

## 1.2.11

- Add one bounded, read-only revision-history tool with provider order, exact revision filtering and opaque continuation. Distinguish malformed pages from valid empty history without weakening unknown-write recovery.
- Preserve allowlisted provider error identifiers, method, stage and status in compact results and mutation receipts; suppress provider bodies and SDK message/details without adding write retries.
- Exclude the provider-owned Dataset source parameter hash from authored-state readback matching. Report Dataset validity separately and support explicit provider validation/source-schema refresh without saving.
- Refresh selected API v3 operation metadata and scoped references for Wizard multi-dataset diagnosis, canonical routes and HTML Page/mailing-list boundaries. Published rendering remains separate from save/publish evidence.

## 1.2.10

- Add compact, revision-guarded dashboard tab edits by widget, layout and connection identity. Preserve complete saved state and verify untouched tabs through the existing writer and receipts without resending whole tabs in tool arguments.
- Support the same compact delta in read-only diffs. Reject missing, ambiguous or repeated identities before dispatch and retain unknown-effect recovery rules.
- Keep dashboard Browser inspection read-only unless UI editing is explicitly requested; route oversized updates through the typed compact tool contract.

## 1.2.9

- Route known targets to addressed reads, reserving workbook inventory for discovery and completeness claims. Clarify bounded handoffs and model-facing projections in the existing skills and tool help.
- Document current-connection readiness, array/key semantics and grain checks before upstream-dependent metric changes, while completing independent authorized work.
- Show subtype-specific Editor tab projection without replacing the provider snapshot. Make publication scope and restoration of only the caller's own delta explicit; retain existing readback and uncertain-effect guarantees.

## 1.2.8

- Distinguish preparation failures from dispatched and composite mutation outcomes. Retain compact create intent before dispatch and require positive non-application evidence before repeating unknown effects.
- Validate inventory containers and identities, retaining partial results and numeric continuation on errors. Bound direct HTTP responses and safe-read budgets, with backoff and Retry-After; writes remain single-attempt.
- Add secret-free credential stage/duration diagnostics, compact full-state diffs, and revision-guarded removal of named dashboard global parameters with absence readback.

## 1.2.7

- Keep cleanup previews stable when Dataset reads reorder known unordered capability and dependency-reference lists. Preserve revision, content, relation, and ordered field checks before deletion.

## 1.2.6

- Match Editor subtype reads against the provider chart family while retaining exact subtype checks and receipt identity. Existing successful subtype creates can reconcile without replaying writes.
- Accept the SDK-supported optional Sources tab for selector drafts.

## 1.2.5

- Derive recovery guidance from confirmed item outcomes for saved results and historical receipt reads. Preserve uncertain effects, exact request bindings and individual batch outcomes.
- Reject invalid cloud entry names before create or rename dispatch using the verified entry contract. Other installations and custom endpoints retain provider validation.

## 1.2.4

- Allow Dataset updates when API v3 explicitly returns a null inner revision, preserving it and requiring the independently checked outer saved revision. Missing and changed revisions still fail before dispatch.

## 1.2.3

- Follow numeric pages for workbook and entry inventories, and stop on repeated continuation tokens with an explicit partial result.
- Retain names, chart renderer subtypes, typed object identities, container membership and revisions in compact inventory and relation results.
- Enforce the provider's workbook-entry page-size bound before dispatch.

## 1.2.2

- Classify credential-helper launch failures, unknown-cause timeouts and explicit login instructions without exposing captured output. Distinguish API authentication failures (401) from scope denials (403).
- Retain failed automatic refresh attempts in the existing runtime; explicit auth recovery retries once and updates both API and SDK credentials without reinstalling.
- Clarify exact-workbook inventory, chart subtype discovery, authorized Editor creation and caller-side projection of privately retained full snapshots.

## 1.2.0

- Migrate to pinned DataLens SDK 3.0.0 and API v3 through the existing typed services, with explicit Cloud/Enterprise configuration.
- Preserve full Dataset state and independent revisions, validate changed Editor tabs, retain V2 Dashboard geometry, and publish exact saved Dashboard/Wizard revisions.
- Use typed bounded preview requests and distinguish empty results from errors. Report the active SDK independently of the installed SDK.
- Adapt the five domain skills for scoped continuation, complete multi-object delivery, HTML/Editor routing and read-only org-scoped RLS resolution.
- Correct unsupported capability claims: Page content authoring requires a verified content readback path and currently rejects before dispatch. Legacy Wizard V2 and Dashboard V1 imports require explicit re-export/migration; Editor/QL publication retains its documented content-publish semantics. See the SDK compatibility note.


## 1.1.1

- Use stable MAJOR.MINOR.PATCH releases. The pyproject version is the release source; an explicit validation/sync step keeps the runtime and plugin aligned.
- Keep SDK 0.9.0 and the existing operation-store format unchanged. Build/process identity remains separate from the release number.

All notable changes to this project are documented in this file. The format is
based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the
project uses [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Optional compact object projections, resumable dashboard dependency reads, and active runtime fingerprints (local 1.1.0 candidate).
- Interprocess operation admission bound to request content, with durable unknown-outcome recovery.

### Fixed

- Full Dataset updates verify business intent separately from provider-owned revision preconditions.
- Partial relation scans and failed dependencies remain partial when composing dashboard snapshots.
- Nested public tool arguments are validated before dispatch; tool errors preserve effect certainty and actionable recovery.
- Retention skips already compacted operation receipts instead of repeatedly rewriting them under the admission lock.
- Scoped skills describe selective reads, continuation notes, complete multi-object coverage, and separate save/data/visual evidence.

## [1.0.0] - 2026-09-07

### Changed

- Replaced the internal task compiler, journal, workflow engine, and generic executors with direct typed DataLens domain operations.
- Added the official `datalens-sdk==0.9.0` path for supported objects and retained narrow Public API adapters only where needed.
- Added eight reusable visual recipes, canonical renderer assets, and automatic generic/user/project/reference/explicit defaults.
- Added typed Dataset-from-existing-source and DashboardTab graph builders, selector/source contracts, artifact-aware batch draft validation, compact recipe handles, and compact operation responses with explicit detailed readback.
- Added saved and published readbacks, revision drift guards, compact uncertain-write reconciliation, and resumable per-object batches.
- Added explicit snapshot backup, dependency-safe cleanup, HTML Page, workbook, and license capability boundaries.

### Added

- Five scoped Codex skills for inspection, Dataset/Wizard work, Editor authoring, dashboard composition, and maintenance.
- A closed 25-tool JSON Schema surface and an implementation-status/owner/boundary map for the 62 public use cases.
- Installed-wheel import and stdio smoke checks that run from an unrelated directory without `PYTHONPATH`.

### Removed

- Removed the legacy task surface, Memory Bank-like runtime state, duplicated executors, private project profiles, and stale generated rule corpora from the shipped package.

## [0.5.0] - 2026-08-06

### Added

- One Wizard-first `standard_dashboard` authoring profile with the protected
  registered renderer for selected Editor capability gaps.
- Renderer Visual Spec with role-owned `embedded_title`, `content_label`,
  `tab_only`, `native_title`, and `tab_strip` title modes.
- A checksum-locked neutral Editor runtime, reusable visual adapters, and
  protected renderer identities.
- Dashboard composition with semantic rows, 36-column geometry, selector
  groups, safe KPI density, schema-valid create/update envelopes, and exact
  mount-to-tab-to-widget-to-chart relationships.
- Final payload and browser-QA attestations bound to routes, runtime, titles,
  selectors, layout, dashboard payload hashes, and saved/published revisions.
- Positive dashboard-shape fixtures and fail-closed regressions for title,
  selector, layout, table, route, runtime, and post-validation drift.

### Changed

- `strict_dashboard` now resolves to `standard_dashboard`; standard KPI,
  table, and chart creation keeps the canonical Wizard technology.
- New and existing dashboards use the same current contract. Historical
  profile names are input aliases that normalize to `standard_dashboard`
  and cannot select old assets, behavior, or project-local descriptors.
- Safe Apply rejects unattested payloads, protected-runtime rewrites,
  post-validation title/layout/selector changes, route substitution, and
  dashboard publication without revision-bound successful browser QA. Nested
  dashboard mount-to-chart bindings and browser evidence artifacts are hash
  checked; `done` requires the matching published revision.
- Browser QA covers every tab from top to full scroll at 720, 1200, and 1440
  pixels and verifies title ownership, selector Clear behavior, layout density,
  clipping, lazy initialization, runtime/network errors, legends, and tooltips.

## [0.4.0] - 2026-07-23

### Added

- Standalone HTML artifact generation and strict sandbox validation through the
  existing bounded authoring and runtime-validation tools.
- Responsive browser evidence for compact and wide dashboard layouts.
- Deterministic visual, value-semantics, hint, and layout-ownership contracts.
- Explicit complete, partial, and unsafe classifications for dashboard snapshots.
- Typed selector contracts with validated parameter bindings and dashboard
  relation checks.
- Dataset-backed Wizard role validation and create/readback evidence.
- A standard dashboard authoring profile that selects registered
  Editor templates for all supported families, fingerprints the complete
  template set and compiled output, and blocks unregistered visual fallbacks.
- Resumable project-live execution IDs for commands longer than the synchronous
  MCP window, with duplicate-launch prevention and replayable final state.
- Hash-locked project-local authoring profiles with exact registered assets,
  portable path containment, and blocked fallback.
- Scoped user-decision patches with project/family/object precedence,
  supersession, deterministic resolution, and plan drift hashes.
- Renderer visual-spec and browser-capture contracts for semantic color
  roles, label overflow, exact tooltip buckets, text truncation, and overlap.

### Changed

- Refreshed the compact documentation/OpenAPI knowledge layer to 91 operations
  and kept the new entry-lock RPCs unsupported until a validated workflow is
  implemented.
- Removed a duplicate full OpenAPI schema map from the runtime package while
  retaining the source-tree reconciliation artifact and the closed validation
  bundle used at runtime.
- Runtime ZIP export now uses the Git publication snapshot and excludes local
  evidence, memory transactions, generated state, and other release-forbidden
  roots.
- Added a bounded semantic maintenance path for merging paired date selectors:
  artifact-backed overlays, exact multi-object locks, all-object publish
  preflight, grouped save/publish readbacks, and runtime-smoke requirements.
- Reduced the standard tool-schema payload while preserving safety-critical
  parameter guidance.
- Exposed validated Wizard/Editor bundle generation on the standard surface
  while keeping low-level request compilation internal.
- Enforced hard inline response budgets with deterministic compaction.
- Reconciled the compiled API contract with the current public OpenAPI snapshot.
- Expanded responsive and signed-value Advanced Editor coverage across every
  implemented chart family.
- Strengthened create, update, publish, snapshot, and portable-wheel verification.
- Aligned whole-object deletion with the manifest-only
  `retire_legacy_objects` contract.
- Accepted direct JavaScript files and widget directories in Editor validation,
  removed false HTML/hint positives, normalized workbook-entry scopes, and
  recognized project manifests separately from runtime configuration.
- Built release wheels from the current non-ignored publication snapshot and
  added an archive-level public-release scan before portable wheel smoke.
- Project-live commands now always use durable worker state with heartbeat,
  restart-safe polling, bounded attachment, and duplicate execution keys.
- Safe Apply now projects fresh merged requests through method schemas,
  distinguishes confirmed writes from verification, and treats received 4xx
  responses as rejected writes rather than unknown outcomes.
- Overlay list handling is explicit and path-scoped, so reviewed layout
  replacement cannot append stale widgets.
- Editor performance findings are advisory unless a runtime contract marks a
  warning rule as blocking; sanitizer and unsupported-runtime errors remain
  blocking.

## [0.3.0] - 2026-07-15

### Added

- Initial public release of the local MCP stdio server.
- Read-only diagnostics, governed authoring plans, guarded safe apply, project
  workflow, and visual-quality tooling for Yandex DataLens development.
- Installation and connection guidance for Codex, Claude, and generic MCP
  clients.
- Packaged, provenance-bearing reference registries compiled from public
  Yandex Cloud documentation.

### Security

- Live writes remain constrained to the target-locked safe-apply workflow;
  explicit hard-off environment values disable write, save, or publish.
- Private workbooks, execution evidence, credentials, and local operator state
  are excluded from the public distribution.

[Unreleased]: https://github.com/ADIKANT/datalens-dev-mcp/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/ADIKANT/datalens-dev-mcp/compare/v0.5.0...v1.0.0
[0.5.0]: https://github.com/ADIKANT/datalens-dev-mcp/compare/v0.4.0...v0.5.0
[0.4.0]: https://github.com/ADIKANT/datalens-dev-mcp/compare/v0.3.0...v0.4.0
[0.3.0]: https://github.com/ADIKANT/datalens-dev-mcp/releases/tag/v0.3.0
