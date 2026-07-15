# MCP-Native Content Model

This repository is the active DataLens development surface. Runtime behavior must be expressed in MCP-native files, not direct copied source trees or sync artifacts.

## Content Classes

| Input type | MCP-native home | Runtime role |
| --- | --- | --- |
| Dashboard development instructions | `src/datalens_dev_mcp/mcp/prompts.py`, `docs/datalens/`, compact routing docs | Prompt and decision support |
| DataLens API behavior | `src/datalens_dev_mcp/api/`, `src/datalens_dev_mcp/mcp/tools/`, `src/datalens_dev_mcp/pipeline/` | MCP tools and safe apply |
| Advanced Editor examples | `templates/`, `examples/gallery/`, chart template configs | Bundle generation |
| Visual governance rules | `docs/datalens/`, `config/`, validators, tests | Deterministic route and style checks |
| Project memory templates | `templates/project/memory-bank/` | Optional project persistence and handoff |
| Raw exports, screenshots, PDFs, courses, Telegram exports | external backup or ignored local materials workspace | Local source material only |

## Rules

- Raw copied materials are not the normal documentation shape.
- If a rule affects runtime behavior, encode it in code, config, schemas, templates, or tests.
- User-facing docs should describe current local MCP workflows, not historical conversion or cache procedures.
- Release-style profile splits are out of scope; this repo exposes one standard local Codex MCP tool surface.

## Promotion Path

1. Read raw evidence only for a specific task.
2. Extract the durable rule, template, method, or example.
3. Commit the extracted form under `docs/datalens/`, `config/`, `templates/`, `examples/`, `schemas/`, or `tests/`.
4. Keep raw evidence external or ignored when it should not become package content.
5. Add a regression test when the rule can be enforced deterministically.
