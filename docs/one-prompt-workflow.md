# One-Prompt Workflow

Prompt:

```text
разработай мне дашборд на основе требований и вот этих данных
```

Expected agent flow:

1. Start pipeline and scaffold project memory.
2. Load startup context from `AGENTS.md` and memory-bank read order.
3. Ingest requirements and data evidence.
4. Build governance brief and route decisions from MCP-native requirements,
   routing, style, and dataviz rules.
5. Generate Wizard-first standard chart plans or capability-gap Editor bundles
   from the canonical registry and gallery/templates.
6. Validate route/editor/payload/secret contracts.
7. Build dry-run payload plan.
8. Create safe apply plan.
9. Stop before live writes unless the user explicitly approves guarded execution.
10. Read back saved/published objects and report after any write.
