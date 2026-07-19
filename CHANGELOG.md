# Changelog

All notable changes to this project are documented in this file. The format is
based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the
project uses [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Versioned responsive browser evidence for compact and wide dashboard layouts.
- Deterministic visual, value-semantics, hint, and layout-ownership contracts.
- Explicit complete, partial, and unsafe classifications for dashboard snapshots.

### Changed

- Reduced the standard tool-schema payload while preserving safety-critical
  parameter guidance.
- Reconciled the compiled API contract with the current public OpenAPI snapshot.
- Improved responsive Advanced Editor templates for time series, KPI, and
  category-comparison charts.

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
