# Changelog

All notable changes to this project are documented in this file. The format is
based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the
project uses [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Changed

- Nothing yet.

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

- Live writes remain disabled by default and require explicit local enablement
  plus the safe-apply workflow.
- Private workbooks, execution evidence, credentials, and local operator state
  are excluded from the public distribution.

[Unreleased]: https://github.com/ADIKANT/datalens-dev-mcp/compare/v0.3.0...HEAD
[0.3.0]: https://github.com/ADIKANT/datalens-dev-mcp/releases/tag/v0.3.0
