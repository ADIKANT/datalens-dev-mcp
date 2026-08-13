# datalens-dev-mcp documentation

[Русский](README.md) · **English** · [Project home](../README_en.md)

[Quick start](../README_en.md#quick-start) · [DataLens access](access_en.md) · [Connect](codex_setup_en.md) · [Tools](tools_en.md) · [JS Cookbook](cookbook/README_en.md) · [Workflows](usage-flow_en.md) · [Sources](sources_en.md) · [Safety](local-only-safety-model_en.md) · [Русский](README.md)

`datalens-dev-mcp` is a local MCP server through which Codex, Claude, and other
MCP clients work with the Yandex DataLens Public API. The user states the task
in plain language, the client selects typed tools, and the server reads objects,
validates changes, saves them, and publishes when requested with result
readback.

It is not a standalone AI assistant or a DataLens interface. The guides below
cover server installation, access, user workflows, supported operations, and
responsibility boundaries.

## Start here

| Goal | Guide |
| --- | --- |
| Install the server | [Quick start](../README_en.md#quick-start) |
| Prepare an IAM token, organization ID, and roles | [DataLens access](access_en.md) |
| Connect Codex | [Codex setup](codex_setup_en.md) |
| Connect Claude or another stdio client | [Client examples](../examples/clients/README.md) |
| Find the right tool | [Guide to all 39 tools](tools_en.md) |
| Start from a ready JavaScript visualization | [JavaScript Visualization Cookbook](cookbook/README_en.md) |
| Create or locally prepare an HTML Page | [HTML generation for DataLens](datalens/html_pages_en.md) |
| Audit without writing | [Read-only audit](usage-flow_en.md#read-only-audit) |
| Build a plan without applying it | [Plan without writing](usage-flow_en.md#plan-without-writing) |
| Save without publishing | [Save without publishing](usage-flow_en.md#save-without-publishing) |
| Apply and publish a change | [Normal save-and-publish change](usage-flow_en.md#normal-save-and-publish-change) |
| Trace packaged reference data | [Official sources](sources_en.md) |

## How it works

```text
User
  -> Codex / Claude / another MCP client
  -> local datalens-dev-mcp
  -> Yandex DataLens Public API

project root
  <- snapshots, plans, checks, readback, and reports
```

A normal change runs through a current object-and-relations read, planning,
validation, save, saved readback, publish from verified saved state, and
published readback. The request selects the stopping point: audits and
diagnostics do not mutate DataLens, `plan-only` stops after planning, and
`save-only` stops after saved readback. Arbitrary whole-object deletion is
unavailable; a manifest `retire_legacy_objects` action requires separate
confirmation of the unchanged plan.

API readback verifies structure. Rendering is checked by the MCP client when a
browser is available or is explicitly reported as unavailable.

## Main guides

- [DataLens access](access_en.md) — Yandex Cloud CLI, organization, IAM token, roles, env file, and access checks.
- [Codex setup](codex_setup_en.md) — `config.toml`, `codex mcp add`, `/mcp`, and connection verification.
- [Tool guide](tools_en.md) — purpose and operation class of all 39 calls.
- [JavaScript Visualization Cookbook](cookbook/README_en.md) — shared Tips, 34 recipes, three linked cases, [interactive synthetic previews](https://adikant.github.io/datalens-dev-mcp/), Sources contracts, and complete copy-ready Editor tab sets.
- [Workflows](usage-flow_en.md) — copyable sequences and prompts.
- [Configuration](configuration_en.md) — local settings and hard-off switches.
- [Safety](local-only-safety-model_en.md) — credential, revision, and deletion safeguards.
- [Chart route policy](route-policy_en.md) — Wizard, Editor, and QL.
- [HTML generation](datalens/html_pages_en.md) — Editor markup versus a
  standalone page, sandbox rules, local validation, and guarded delivery.
- [Safe apply](safe-apply_en.md) — save, readback, and publishing.

## Technical documentation

- [Architecture](architecture.md)
- [Exact MCP catalog](mcp/tools.md)
- [Response contracts](mcp/response_contracts.md)
- [DataLens API coverage](datalens/api_contract_coverage.md)
- [Reference-data provenance](source_provenance.md)

The standard `tools/list` contains 39 tools. Exact JSON schemas for the installed version are available directly through the MCP client and are summarized in the [technical catalog](mcp/tools.md).
