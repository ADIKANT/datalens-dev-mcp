# AGENTS.md

This repository owns the local `datalens-dev-mcp` Python stdio server.

## Ordinary dashboard work

- Work from the exact dashboard project or subproject root. Use its local context; do not substitute the server repository.
- Use the installed DataLens domain skills and typed public tools. Do not read server source or run server tests for an ordinary dashboard request.
- Use scoped API reads, save/readback, publish-from-saved, and published readback. When rendered evidence is required, use Browser read-only after API and applicable data checks.
- Read-only analysis does not need confirmation. Show one compact plan before a substantial mutation; one confirmation covers the unchanged plan. Destructive actions always require exact-object confirmation.
- Preserve an existing object's technology. Use Wizard for new standard charts, Editor/JavaScript only by direct request or a documented gap, and QL only by direct request.
- Never guess IDs, expose secrets, change permissions, or write to production or unowned objects.

## Server maintenance

- Read only the owners and documentation causally required for the defect. Preserve useful dirty work and keep raw corpora, sessions, runtime receipts, caches, credentials, and private object data out of Git.
- Keep one typed backend and the direct authoring/read/write services. Do not add a task compiler, journal/workflow, generic executor, or parallel runtime framework.
- Verify a real fail-before, apply one coherent owner fix, then run focused and affected tests. Do not run a full suite or build repeatedly while diagnosing.
- Treat commits, pull requests, issues, and release notes as public. Use generic behavior and synthetic evidence; never publish private names, IDs, prompts, local paths, or credential material.

## Release and final delivery

- Run the offline, affected, autonomy, and final full acceptance contours once the behavior is frozen. A live claim requires a controlled run-owned canary and cleanup.
- Deliver through a feature branch and Pull Request; never direct-push or force-push `main`.
- After merge, build and install from clean exact `origin/main`, install the plugin skills, verify import from `site-packages` without `PYTHONPATH=src`, the closed tool surface, auth/read probes, and an ordinary task from an exact dashboard subproject.
