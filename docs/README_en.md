# datalens-dev-mcp documentation

[Русский](README.md) · **English** · [Project home](../README_en.md)

[Install](codex_setup_en.md) · [Tools](tools_en.md) · [Usage flow](usage-flow_en.md) · [Official sources](sources_en.md) · [Safety](local-only-safety-model.md)

This section explains the public surface of the local MCP server: how to connect it, which problems its 38 standard tools solve, how work proceeds from a read-only check to guarded publishing, and which official DataLens materials underpin the API contracts and packaged reference registries.

## Start here

| I want to… | Open |
| --- | --- |
| Install the server and connect Codex | [Codex setup](codex_setup_en.md) |
| Connect Claude or another stdio client | [README: connect an MCP client](../README_en.md#connect-an-mcp-client) |
| Understand a particular tool | [Guide to the 38 public tools](tools_en.md) |
| Run a read-only dashboard audit | [Flow: read-only audit](usage-flow_en.md#2-read-only-audit) |
| Plan a change without writing | [Flow: plan-only](usage-flow_en.md#3-plan-only) |
| Save and publish safely | [Flow: guarded save and publish](usage-flow_en.md#4-guarded-save-and-publish) |
| Trace a capability to its basis | [Official source map](sources_en.md) |
| Understand a write block | [Safe Apply](safe-apply.md) |
| Inspect exact MCP inputs and outputs | [Technical tool catalog](mcp/tools.md) and [response contracts](mcp/response_contracts.md) |

## Primary user path

```text
MCP client
  -> dl_runtime_status / dl_auth_probe
  -> workbook and object reads
  -> dashboard snapshot and relation evidence
  -> route, object, and project validation
  -> payload plan and safe-apply plan
  -> guarded save
  -> saved readback
  -> publish-from-saved when allowed
  -> published readback and runtime/browser QA
```

The DataLens runtime starts read-only. Local tools can create plans and reports inside `--project-root`, but a live mutation requires independent write/save/publish gates, approval, a fresh read, and readback.

## Documentation by topic

### User guides

- [Tools](tools_en.md) — what every public tool does and when to use it.
- [Usage flow](usage-flow_en.md) — end-to-end scenarios and copyable prompts.
- [Codex setup](codex_setup_en.md) — app, CLI, `config.toml`, `/mcp`, and troubleshooting.
- [Official sources](sources_en.md) — DataLens docs, Public API, Editor, and provenance.

### Policy and safety

- [Configuration](configuration.md)
- [Local-only safety model](local-only-safety-model.md)
- [Route policy](route-policy.md)
- [Safe apply](safe-apply.md)
- [Policy vocabulary](policy_vocabulary.md)

### Technical reference

- [Architecture](architecture.md)
- [MCP tools](mcp/tools.md)
- [Response contracts](mcp/response_contracts.md)
- [Tool-selection policy](mcp/tool_selection_policy.md)
- [API contract coverage](datalens/api_contract_coverage.md)
- [Source provenance](source_provenance.md)

## Boundaries

- Normal `tools/list` returns one standard surface of 38 tools.
- Compatibility/test-only tools are not a user profile and do not belong in the recommended flow.
- Wizard is the default route for new standard charts; JavaScript requires a direct request or capability gap; QL requires a direct request.
- Delete, move, and permission mutations are closed in normal workflows. Named removal uses the separate `retire_legacy_objects` lifecycle only.
- Raw documentation pages, books, courses, private exports, and credentials are not stored in the repository.
