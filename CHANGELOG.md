# Changelog

All notable changes to this project are documented in this file. The format is
based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the
project uses [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.4.0] - 2026-07-23

### Added

- Standalone HTML artifact generation and strict sandbox validation through the
  existing bounded authoring and runtime-validation tools.
- Versioned responsive browser evidence for compact and wide dashboard layouts.
- Deterministic visual, value-semantics, hint, and layout-ownership contracts.
- Explicit complete, partial, and unsafe classifications for dashboard snapshots.
- Typed selector contracts with validated parameter bindings and dashboard
  relation checks.
- Dataset-backed Wizard role validation and create/readback evidence.
- A versioned `standard_editor_v1` authoring profile that selects registered
  Editor templates for all supported families, fingerprints the complete
  template set and compiled output, and blocks unregistered visual fallbacks.
- Resumable project-live execution IDs for commands longer than the synchronous
  MCP window, with duplicate-launch prevention and replayable final state.
- Hash-locked project-local authoring profiles with exact registered assets,
  portable path containment, and blocked fallback.
- Scoped user-decision patches with project/family/object precedence,
  supersession, deterministic resolution, and plan drift hashes.
- Renderer visual-spec v3 and browser-capture v3 contracts for semantic color
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

[Unreleased]: https://github.com/ADIKANT/datalens-dev-mcp/compare/v0.4.0...HEAD
[0.4.0]: https://github.com/ADIKANT/datalens-dev-mcp/compare/v0.3.0...v0.4.0
[0.3.0]: https://github.com/ADIKANT/datalens-dev-mcp/releases/tag/v0.3.0
