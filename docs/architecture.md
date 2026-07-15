# Architecture

`datalens-dev-mcp` is a local stdio MCP server with an outbound DataLens API client. The MCP client owns the process lifecycle; the server does not open an HTTP port or provide a hosted control plane.

## Runtime flow

```text
MCP client
  -> stdio JSON-RPC dispatcher
  -> registered prompts, resources, and tools
  -> planning / validation / safe-apply pipeline
  -> sanitized DataLens RPC client
  -> DataLens API

Project root
  <-> requirements, plans, snapshots, validation evidence, reports

External env file
  -> credentials and explicit runtime gates
```

Stdout is reserved for MCP JSON-RPC. Logs and diagnostics go to stderr. Credentials are loaded locally and must not appear in responses, generated artifacts, or logs.

## Package layers

### MCP surface

`src/datalens_dev_mcp/server.py` implements protocol initialization and dispatch for tools, prompts, and resources. `src/datalens_dev_mcp/mcp/` contains the public MCP contracts, response projection, registry policy, and tool implementations.

The standard surface combines read-only diagnostics, object inspection, project planning, validation, and guarded mutation tools. Hidden compatibility helpers are not part of normal client discovery.

### Planning and governance pipeline

`src/datalens_dev_mcp/pipeline/` turns a user request and fresh object evidence into route decisions, project artifacts, payload plans, safe-apply plans, readback checks, and deployment reports.

Important boundaries are represented explicitly:

- user intent is separate from runtime permission;
- a local project path is separate from a DataLens object ID;
- a planned payload is separate from an executed write;
- saved readback is separate from published readback;
- static validation is separate from live and browser evidence.

### DataLens API layer

`src/datalens_dev_mcp/api/` contains authentication, method metadata, request compilation, schema checks, transport behavior, and sanitized errors. The server uses a curated method catalog and does not expose arbitrary network or shell access through the normal tool surface.

### Authoring and validation

`src/datalens_dev_mcp/editor/` compiles and validates parameterized Advanced Editor bundles. `src/datalens_dev_mcp/validators/` checks routes, project artifacts, dashboard payloads, SQL, internal names, secrets, redaction, and URI safety.

Native Wizard charts remain the default for standard supported visualizations. Advanced Editor routes are selected only for explicit requests or registered capability gaps. QL requires an explicit QL request.

### Reference data and packaged resources

`src/datalens_dev_mcp/knowledge/` provides bounded lookup and reference services. Versioned resources under `src/datalens_dev_mcp/assets/` are packaged with the wheel so a normal installation does not depend on a separate local source archive.

The compiled DataLens reference data retains source metadata. Third-party source and license details are documented in `THIRD_PARTY_NOTICES.md`; it is not a hidden runtime download.

## Repository layout

| Path | Responsibility |
| --- | --- |
| `src/datalens_dev_mcp/` | Installable Python runtime |
| `config/` | Versioned behavior, routing, style, and API policy |
| `schemas/` | JSON Schemas for inputs and generated artifacts |
| `templates/` | Parameterized authoring and project templates |
| `docs/` | Public operator and contributor documentation |
| `examples/` | Synthetic examples and client configurations |
| `scripts/` | Reproducible offline checks and maintenance tasks |
| `tests/` | Unit and offline integration coverage |

Runtime code reads packaged assets rather than assuming the checkout's current working directory. `--project-root` intentionally selects a separate local workspace. An optional `--local-config` path can override project-local preferences, but config cannot enable writes.

## Safety model

The default state is read-only. Opening the write env flag does not directly call the API. Mutation requires an approved safe-apply plan, a known target, fresh read/revision preservation, explicit save permission, saved readback, and any additional delivery gate required by the request.

Publish is a separate capability. Planning, review, draft, save-only, or no-publish intent prevents it even when other runtime flags are present. Delete, move, and permission operations remain outside the normal write lane.

The server's local filesystem authority is bounded by the selected project root and explicit paths accepted by individual tools. Secrets belong in an external env file; generated artifacts and MCP responses are subject to redaction and secret scanning.

See `docs/local-only-safety-model.md`, `docs/safe-apply.md`, `docs/route-policy.md`, and `docs/mcp/response_contracts.md` for the normative contracts.

## Distribution boundary

The supported distribution is a Python package that runs over stdio. The repository does not include a hosted HTTP/SSE deployment, remote credential broker, browser extension, or managed service. MCP clients may be different, but they all start the same local executable with command, args, and environment configuration.
