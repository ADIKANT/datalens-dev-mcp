---
name: datalens-inspect
description: Use when inspecting DataLens authentication, workbooks, dashboards, charts, datasets, connections, relations, or current errors without mutation.
---

# DataLens Inspect

Use direct scoped reads. Start from an exact URL or object ID, read only required dependencies, distinguish saved from published state, and report partial inventory explicitly. A legacy manifest is never required. Never create project files during an audit. For direct-source Editor charts, report static/source validation separately from live result validation.

Use this skill for inspection without mutation. If the request changes a Dataset/Wizard, dashboard, Editor chart, or maintenance scope, route to that domain skill after discovery and load only its addressed reference.

Read [references/direct-reads.md](references/direct-reads.md) before selecting operations or claiming completeness.
