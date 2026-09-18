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

For a token renewal request or credential recovery within an authorized DataLens task, use `dl_auth_refresh` with its default `allow_browser=true`. It runs the existing `yc` profile's supported token command and allows **the system external browser** to complete the configured provider/SSO sign-in, waiting up to 120 seconds. An existing browser session may authenticate automatically; ask the user only for actual password/MFA or another unresolved boundary. Announce the browser sign-in and continue when the session already authorizes it; do not add another plan/login permission question. Do not change account/profile, extract browser cookies, copy callback URLs into an embedded browser, or print captured helper output. Set `allow_browser=false` only for an explicit browser restriction or a noninteractive-only request; that mode retains the 15-second bound.

Automatic refresh on bootstrap/401 stays noninteractive. A failed attempt is retained in the current runtime, so the next object read does not start the same refresh again. A `credential_refresh_timeout` at `stage=credential_helper` does not establish a network failure or forbidden login: use the explicit browser-enabled recovery once when authorized. The `browser_credential_helper` stage means browser sign-in was allowed, not proof that a window opened or authentication succeeded. On its timeout, inspect pending user login/MFA and bounded helper/network evidence; do not keep retrying an unchanged failure. For `interactive_login_required` that persists after recovery, follow the installed CLI's supported same-profile setup. For a helper launch or unclassified failure, establish the local cause without exposing secrets.

Success updates both API and SDK clients in the running process and verifies API access; it requires no reinstall or token transfer. Resume the original safe read. A successful browser login alone is not an API probe. A dashboard Browser read-only rule does not prohibit this supported authentication command. Real host approvals remain separate: explain the configured SSO purpose and current authorization, respect an actual denial, and never change host policy or switch surfaces to bypass it. Do not retry an unknown write during auth recovery: follow [repeat-effect recovery](../../datalens-dashboard/references/authorized-scope.md#unknown-outcomes-and-repeat-effects).

## Objects and containers

A connection supplies source access; a dataset models fields, joins, parameters and row access; a chart visualizes data; a dashboard arranges charts and selectors. Wizard usually binds a dataset; QL queries a connection; Editor uses JavaScript and its declared sources. Preserve an existing chart's technology and use QL only when requested.

Collections/workbooks organize entries separately from their data dependencies. Legacy folder/path organization may coexist or be absent. Establish the actual container from current reads, keeping organization, workbook, entry ID, object type, branch and revisions together. A workbook name alone is not target identity.

## Choose the requested interface

Ordinary DataLens work uses this plugin's typed `dl_*` tools, current project defaults and recipes. Read addressed schemas/references only as needed. Unknown operations require a precise unsupported outcome or a separately reviewed typed extension; a generic gateway or ad hoc script cannot bypass mutation receipts/readback.

An explicit independent Python SDK scripting request is separate: inspect its selected interpreter, package version and environment, then consult that installed version's docs. Do not bootstrap, install or upgrade dependencies in a dashboard project for a metadata read. For SDK 3.0.0, `agent_skill_paths()` exists and returns skill directories; verify that callable in the actual installed package before using it on another version. Read only the relevant returned reference as technical documentation. Package preflight/bootstrap scripts may write files or install dependencies; reading documentation is not authorization to run them.

The version-bound API/builders reference is SDK tag `v3.0.0`, not the wrapper's stale 0.x description. Check active SDK/API compatibility during migration or a relevant diagnosis, not on every tool call. This guidance imports neither the upstream blanket script route nor its Browser and business-metric exclusions: this plugin retains BI-semantic checks and read-only rendered verification requested by the task.
