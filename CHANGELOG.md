# Changelog

All notable changes to this project are documented in this file. The format is
based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the
project uses [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

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

### Changed

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

[Unreleased]: https://github.com/ADIKANT/datalens-dev-mcp/compare/v0.3.0...HEAD
[0.3.0]: https://github.com/ADIKANT/datalens-dev-mcp/releases/tag/v0.3.0
