# Installation, entities and interfaces

Selectively adapted from upstream DataLens documentation; routing changed for this plugin. Copyright 2026 YANDEX LLC, Apache-2.0. Exact sources and modifications: [upstream provenance](upstream-provenance.md).

## Establish only missing context

Use the exact dashboard subproject's current configuration and installed tool capability information. Reuse known API endpoint, installation and organization without asking again. A harmless auth probe tests access, not object inventory. Keep tokens out of output; inspect only non-secret configuration fields.

| Installation | Context to establish |
| --- | --- |
| Yandex Cloud | Configured API endpoint, IAM provider and organization ID; identity is scoped to that organization. |
| Enterprise / self-hosted | Deployment's configured API endpoint and authentication; UI hostname does not determine the API host. |
| Internal installation | Its documented API/auth and supported capabilities; do not transplant cloud IDs or defaults. |

If the API endpoint or target organization remains unresolved after scoped configuration reads, ask for that missing value. Never fall back to cloud merely because another installation is unavailable. An upstream example does not certify this installation's endpoint, API version or capability.

## Authentication recovery

`dl_auth_check` makes a minimal API read. Distinguish a helper that cannot start, explicit interactive-login evidence, a timeout of unknown cause, an API 401 (`authentication_failed`) and a scope 403 (`permission_denied`). None establishes that a workbook is missing. Helper errors expose only an allowlisted code, exit status and diagnostic ID; never print captured stdout/stderr or tokens.

After a failed automatic helper attempt the current runtime retains the failure, so inspecting the next object does not start the same refresh again. Use `dl_auth_refresh` for one deliberate recovery attempt after addressing the cause. Success updates both API and SDK clients in the running process and verifies API access; it requires no reinstall. Resume the original read afterward. A changed configured credential/runtime identity also gets its own recovery state.

For `interactive_login_required`, follow the installed `yc` CLI's supported sign-in for the same configured account/profile, requesting human login/MFA only when needed. For `credential_refresh_timeout`, first inspect bounded executable/launch and network evidence; do not infer login from elapsed time alone. For an unclassified helper failure, use safe local diagnostics to establish the cause. A successful UI login is not an API probe. Do not retry a write with unknown outcome during auth recovery; reconcile its operation and target first.

## Objects and containers

A connection supplies source access; a dataset models fields, joins, parameters and row access; a chart visualizes data; a dashboard arranges charts and selectors. Wizard usually binds a dataset; QL queries a connection; Editor uses JavaScript and its declared sources. Preserve an existing chart's technology and use QL only when requested.

Collections/workbooks organize entries separately from their data dependencies. Legacy folder/path organization may coexist or be absent. Establish the actual container from current reads, keeping organization, workbook, entry ID, object type, branch and revisions together. A workbook name alone is not target identity.

## Choose the requested interface

Ordinary DataLens work uses this plugin's typed `dl_*` tools, current project defaults and recipes. Read addressed schemas/references only as needed. Unknown operations require a precise unsupported outcome or a separately reviewed typed extension; a generic gateway or ad hoc script cannot bypass mutation receipts/readback.

An explicit independent Python SDK scripting request is separate: inspect its selected interpreter, package version and environment, then consult that installed version's docs. Do not bootstrap, install or upgrade dependencies in a dashboard project for a metadata read. For SDK 3.0.0, `agent_skill_paths()` exists and returns skill directories; verify that callable in the actual installed package before using it on another version. Read only the relevant returned reference as technical documentation. Package preflight/bootstrap scripts may write files or install dependencies; reading documentation is not authorization to run them.

The version-bound API/builders reference is SDK tag `v3.0.0`, not the wrapper's stale 0.x description. Check active SDK/API compatibility during migration or a relevant diagnosis, not on every tool call. This guidance imports neither the upstream blanket script route nor its Browser and business-metric exclusions: this plugin retains BI-semantic checks and read-only rendered verification requested by the task.
