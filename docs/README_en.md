# datalens-dev-mcp documentation

[Русский](README.md) · **English** · [Project home](../README_en.md)

[Quick start](../README_en.md#quick-start) · [DataLens access](access_en.md) · [Connect](codex_setup_en.md) · [Tools](tools_en.md) · [Workflows](usage-flow_en.md) · [Sources](sources_en.md) · [Safety](local-only-safety-model_en.md) · [Русский](README.md)

These guides cover installation, DataLens access, and the complete workflow from reading objects to saving and publishing changes.

## Start here

| Goal | Guide |
| --- | --- |
| Install the server | [Quick start](../README_en.md#quick-start) |
| Prepare an IAM token, organization ID, and roles | [DataLens access](access_en.md) |
| Connect Codex | [Codex setup](codex_setup_en.md) |
| Connect Claude or another stdio client | [Client examples](../examples/clients/README.md) |
| Find the right tool | [Guide to all 38 tools](tools_en.md) |
| Create a standalone HTML artifact | [HTML generation for DataLens](datalens/html_pages_en.md) |
| Audit without writing | [Read-only audit](usage-flow_en.md#read-only-audit) |
| Build a plan without applying it | [Plan without writing](usage-flow_en.md#plan-without-writing) |
| Save without publishing | [Save without publishing](usage-flow_en.md#save-without-publishing) |
| Apply and publish a change | [Normal save-and-publish change](usage-flow_en.md#normal-save-and-publish-change) |
| Trace packaged reference data | [Official sources](sources_en.md) |

## Normal change flow

```text
connect the client
  -> dl_runtime_status and dl_auth_probe
  -> find the workbook and target object
  -> read current state and relations
  -> plan and validate the request
  -> save
  -> read saved state
  -> publish from saved state
  -> read published state
  -> verify the result in DataLens
```

The user request selects the mode. Audits and diagnostics do not mutate DataLens. `plan-only` stops after planning, and `save-only` stops after saved readback. Create, fix, update, enhance, and redesign requests for a known target run through the complete flow without another prompt before save or publish. Arbitrary whole-object deletion is unavailable; a manifest `retire_legacy_objects` action requires separate confirmation of the unchanged plan.

## Main guides

- [DataLens access](access_en.md) — Yandex Cloud CLI, organization, IAM token, roles, env file, and access checks.
- [Codex setup](codex_setup_en.md) — `config.toml`, `codex mcp add`, `/mcp`, and connection verification.
- [Tool guide](tools_en.md) — purpose and operation class of all 38 calls.
- [Workflows](usage-flow_en.md) — copyable sequences and prompts.
- [Configuration](configuration_en.md) — local settings and hard-off switches.
- [Safety](local-only-safety-model_en.md) — credential, revision, and deletion safeguards.
- [Chart route policy](route-policy_en.md) — Wizard, Editor, and QL.
- [HTML generation](datalens/html_pages_en.md) — Editor markup versus a
  standalone page, sandbox rules, and local validation.
- [Safe apply](safe-apply_en.md) — save, readback, and publishing.

## Technical documentation

- [Architecture](architecture.md)
- [Exact MCP catalog](mcp/tools.md)
- [Response contracts](mcp/response_contracts.md)
- [DataLens API coverage](datalens/api_contract_coverage.md)
- [Reference-data provenance](source_provenance.md)

The standard `tools/list` contains 38 tools. Exact JSON schemas for the installed version are available directly through the MCP client and are summarized in the [technical catalog](mcp/tools.md).
