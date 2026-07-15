# Runtime Instruction Model

The MCP runtime prompt layer should be compact. Long reference material belongs
in docs, configs, schemas, templates, resources, and tests.

## Canonical Runtime Directive

Every MCP runtime prompt starts from one shared directive:

- templates-first.
- no removed chart routes.
- Wizard path is separate from Advanced Editor.
- do not invent Advanced Editor methods.
- enforce `render`/`wrapFn` through templates and validators.
- use style tokens.
- persistent Markdown requirements before implementation.
- fail with clear missing-input diagnostics.
- no legacy cache sync.

## Instruction Placement

| Instruction type | Home |
| --- | --- |
| Tool orchestration order | Runtime prompt text |
| Route and chart support | `docs/route-policy.md`, `docs/datalens/`, route validators |
| Advanced Editor methods | `docs/datalens/advanced_editor_methods.md`, packaged registries, editor validators |
| Template and style behavior | `templates/`, `examples/gallery/`, `config/`, tests |
| Selector/dashboard relations | schemas, relation docs, validators |
| Requirements persistence | project memory templates and pipeline tools |
| Generated validation evidence | ignored `artifacts/` workspace |
| Raw material context | ignored `materials/` workspace |

## Review Rules

- Delete duplicate prose when an enforceable schema/test exists.
- Replace repeated long text with the shared directive plus route-specific
  action steps.
- Keep runtime prompt text under 900 characters per prompt unless a concrete MCP
  protocol need requires more.
- Do not move sensitive raw evidence into runtime prompts.
- Do not keep legacy plugin-cache sync instructions in active prompts.
