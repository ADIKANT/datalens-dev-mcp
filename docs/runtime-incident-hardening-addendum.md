# DataLens Dev MCP: runtime incident hardening addendum

**Date:** 2026-08-27  
**Purpose:** extend the public autonomy hardening goal with public-safe defects reproduced from real MCP sessions.  
**Execution:** complete these work packages after WP-09 and before freezing the final acceptance candidate.

The evidence behind this addendum is represented only by synthetic fixtures and generic contracts. Private workbook names, object identifiers, local paths, and source-session content are not part of the repository.

## WP-10. Provider request, identity, and readback normalization

```text
Branch: codex/dlm-runtime-incident-hardening
PR title: Normalize provider writes and Safe Apply readback evidence
```

### Goal

Make valid create and update requests deterministic across provider-managed defaults without weakening write safety or replaying ambiguous writes.

### Create

```text
tests/unit/test_runtime_provider_normalization.py
```

### Change

```text
src/datalens_dev_mcp/api/client.py
src/datalens_dev_mcp/api/request_compiler.py
src/datalens_dev_mcp/pipeline/safe_apply.py
src/datalens_dev_mcp/server.py
```

### Implementation

- Retry HTTP 500 only for bounded read-only calls, under the existing transient-read budget. Never retry a write.
- Preserve the top-level identity returned by create methods when it is stronger than a nested payload object.
- Normalize only documented provider-required structural defaults:
  - an absent Editor `entry.data.controls` becomes a deterministic empty controls module;
  - an absent Dashboard control-item `defaults` becomes an empty object.
- Compare Wizard readback semantically:
  - ignore request-only `template` and provider-managed `data.version`;
  - ignore an absent provider default only when the requested value was null or empty;
  - retain every explicit non-empty semantic value.
- Validate publish provenance against the fresh saved source before the write, then require post-publish readback to match the write revision and saved/published identities to converge. Do not require the provider's new published revision to equal the pre-publish saved revision.
- Expose every already-supported structured `dl_task_start.context` field in the public tool schema.
- Keep provider semantic roles (`DIMENSION`/`MEASURE`) separate from physical `data_type` so typed profiles retain dates and measures.
- Resolve dataset IDs embedded in Editor metadata or source strings only when workbook inventory proves the referenced object is a dataset.
- Carry a conflict-free scalar dashboard selector default into a dataset probe only when the chart binding proves that parameter GUID; never guess a missing or multi-value parameter.

### Positive tests

- A read-only HTTP 500 is retried within budget and succeeds.
- A create response with top-level `id` and a nested object yields the top-level created identity.
- Minimal Editor and Dashboard create payloads receive only the required empty structural defaults.
- Wizard readback with provider version/default fields remains content-equivalent.
- Publish readback with the write revision and converged saved/published identities verifies successfully.
- A live-shaped field with a semantic `type` and physical `data_type` keeps both meanings.
- An Editor string dependency is accepted only when the exact ID is typed as a dataset by workbook inventory.
- A parameterized dataset probe uses its chart-bound selector default, while conflicting, unrelated, and multi-value defaults remain absent.

### Negative tests

- HTTP 500 on a write is attempted exactly once.
- A non-empty explicit Wizard setting remains part of semantic comparison.
- Create without any stable identity remains blocked as `missing_created_identity`.
- Publish with stale pre-write source, mismatched write revision, or divergent saved/published identity remains blocked.
- Normalization never invents chart logic, selector values, dashboard layout, or business semantics.

### Acceptance

```bash
python3 -m pytest -q tests/unit/test_runtime_provider_normalization.py
python3 -m pytest -q tests/unit/test_api_scheduler_and_batch.py tests/unit/test_runtime_safe_apply_incident_contracts.py
```

### Completion gate

- Every reproduced provider mismatch has a synthetic regression.
- The regression proves zero write retries and unchanged stale-revision gates.
- Public tool-schema readback advertises the structured context accepted by the implementation.

### Forbidden in WP-10

- no provider-specific business values;
- no silent broadening of equality into unordered or lossy comparison;
- no retry of create, update, save, or publish;
- no live object identifiers in fixtures or documentation.

## WP-11. Workbook-scoped typed create workflow

```text
Branch: codex/dlm-public-create-manifest
PR title: Add a typed workbook-scoped public create workflow
```

### Goal

Allow a public `dl_task_start` create request with a known workbook to reach an immutable Safe Apply plan without selecting an unrelated existing dashboard or falling into the existing-object semantic-update planner.

### Create

```text
src/datalens_dev_mcp/pipeline/create_manifest.py
src/datalens_dev_mcp/assets/schemas/public-create-manifest.schema.json
schemas/public-create-manifest.schema.json
tests/unit/test_public_create_manifest.py
tests/integration/test_public_create_workflow.py
```

### Change

```text
src/datalens_dev_mcp/mcp/tools/tasks.py
src/datalens_dev_mcp/pipeline/target_discovery.py
src/datalens_dev_mcp/pipeline/task_planning_stage_services.py
src/datalens_dev_mcp/pipeline/public_plan_builder.py
src/datalens_dev_mcp/pipeline/project_journal.py
src/datalens_dev_mcp/server.py
docs/usage-flow.md
docs/tools.md
docs/mcp/tools.md
```

### Manifest contract

The request supplies a relative `create_manifest` path inside `project_root`. The manifest is versioned and contains an ordered, bounded set of typed create objects. Each object has a stable local key, object type, canonical route, display name, relative payload artifact, and explicit dependencies.

The server resolves and hashes the manifest and every payload before the first write, copies sanitized immutable inputs into the task journal, validates routes and dependency order, and binds the resulting hash to the task contract and plan. Absolute paths, symlink escapes, unsupported object types, QL without a direct QL request, and unresolved dependencies fail closed.

### Implementation

- Workbook-only create discovery inventories the exact workbook and binds an inventory snapshot; it does not guess an existing dashboard target.
- Create planning is separate from existing-object semantic update planning.
- Canonical create routes are dataset, Wizard chart, Editor chart, Markdown page, and dashboard. QL remains direct-request-only.
- Every create action has fresh inventory read, projected request validation, exact created-identity extraction, saved readback, and optional publish from verified saved state.
- Dependent object references use declared placeholders. A stage is materialized only after all dependency identities are verified; its resolved payload and hash are journaled before that stage's first write.
- Resume reconciles completed create identities from readback and never blindly recreates an object.
- A duplicate key or provider uniqueness conflict enters partial-create reconciliation and cannot fall back to a new name or technology.

### Positive tests

- Workbook plus a single independent dataset manifest reaches `plan_ready` without a dashboard target.
- A synthetic dataset -> chart -> dashboard manifest resolves identities stage by stage and completes save/readback/publish.
- Process restart after an intermediate create resumes from journaled identities without duplicate writes.
- Public tool discovery exposes `create_manifest`, semantic changes, acceptance, scope, portfolio root, and discovery budget.

### Negative tests

- Path escape, symlink escape, manifest drift, payload drift, dependency cycle, unresolved placeholder, and unsupported route block before the affected write.
- Multiple or zero existing dashboards do not affect workbook-scoped create discovery.
- A stale workbook inventory blocks before create.
- QL is never inferred as a fallback.
- Partial or ambiguous create never advances to dependent objects or publish.

### Acceptance

```bash
python3 -m pytest -q tests/unit/test_public_create_manifest.py
python3 -m pytest -q tests/integration/test_public_create_workflow.py
python3 scripts/run_affected_acceptance.py
```

### Completion gate

- One installed public stdio canary creates a synthetic multi-object chain in a dedicated test workbook, proves saved and published readback, restarts, resumes, and produces no duplicate object.
- The receipt binds exact head, source tree, manifest, payloads, created identities, revisions, and publication tree.
- Cleanup, if requested, is a separately authorized exact-ID operation; successful creation is not hidden by cleanup status.

### Forbidden in WP-11

- no implicit existing-dashboard selection for create;
- no untyped arbitrary method/payload list;
- no write before the current stage is fully resolved and validated;
- no automatic QL fallback;
- no retry of an ambiguous write;
- no whole-object deletion.

## WP-12. Incident corpus and final installed acceptance

```text
Branch: codex/dlm-public-autonomy-final-incidents
PR title: Prove public autonomy against runtime incident regressions
```

### Goal

Bind the incident fixes, the `getDatasetData` context addendum, and the original public autonomy plan to one frozen exact-head candidate.

### Create

```text
tests/regression/runtime_incidents/
scripts/run_runtime_incident_acceptance.py
```

### Change

```text
scripts/run_affected_acceptance.py
scripts/run_autonomy_acceptance.py
scripts/run_full_acceptance.py
docs/public-autonomy-canary.md
```

### Implementation

- Convert each server-owned incident into a sanitized deterministic fixture.
- Preserve environment and operator errors as explicit non-product exclusions.
- Run `getDatasetData` read-only context and assertion probes across several existing dashboards with different dataset shapes; store only bounded redacted receipts outside the tracked repository.
- Freeze the source tree before the final full suite. Any code, schema, fixture, or documentation change invalidates all previous full-suite and live receipts.

### Positive tests

- Every incident fixture reaches the expected normalized request, identity, or verified readback state.
- Multiple dashboard probes demonstrate field resolution, positional-row normalization, observed types, limitations, and deterministic query hashes.
- Installed stdio reports exactly the eight public tools and the same build identity as the frozen source.

### Negative tests

- Previously observed false-green and false-blocked variants replay to their exact fail-closed classifications.
- Experimental dataset-data unavailability produces explicit fallback limitations, never invented data evidence.
- Private source strings and live identifiers are absent from the tracked tree, wheel, receipts intended for publication, and Git metadata.

### Acceptance

```bash
python3 scripts/run_runtime_incident_acceptance.py
python3 scripts/run_affected_acceptance.py
python3 scripts/run_autonomy_acceptance.py
python3 scripts/run_full_acceptance.py --sharded
python3 scripts/run_offline_acceptance.py
```

### Completion gate

- All commands pass from one unchanged exact head.
- Installed readback and controlled live canaries bind that same head and tree.
- PR checks pass, the PR is merged, the installed artifact is rebuilt from the merged head, and a new process reports the merged identity.

### Forbidden in WP-12

- no acceptance receipt from an earlier tree;
- no private workbook names, object IDs, local paths, or raw rows in public artifacts;
- no claim that fallback evidence is live typed data;
- no browser automation for data proof.
