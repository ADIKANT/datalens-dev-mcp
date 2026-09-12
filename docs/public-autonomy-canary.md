# Host evaluation and controlled live acceptance

The current runtime uses direct typed `dl_*` tools and operation receipts. Historical `autonomous-v2`, `dl_task_*`, eight-tool and immutable-plan canary instructions do not apply. This repository does not currently provide a runnable host-evaluation or live-canary runner; do not invoke removed scripts or represent fixtures as a completed run.

## Local versus host proof

The replacement tests exercise bounded local contracts. `scripts/installed_smoke.py` checks an installed package outside source imports. Neither proves that a host selected the right skill, completed a multi-workbook task, performed a provider write, or rendered a correct dashboard.

Evaluate baseline and candidate on the same actual host/model/reasoning, permissions, tool environment and synthetic fixtures. Keep expected outcomes and withheld paraphrases out of the evaluated model's context. Cover configured Enterprise metadata read, Page versus Editor HTML, ambiguous read-only cloud RLS lookup, six-workbook save-only completion with one missing dependency, continuation after revision drift, scope cancellation during an unknown write, a concise metadata change, and correct readback with a visibly broken render.

Record case, tested commit, active package/build, host version/model/reasoning (unexposed fields stay `not_exposed`), fixture hash, operation/tool, observed outcome, evidence tier, output reference, limitations and cleanup. Measure bytes separately from actual tokens; unavailable usage stays unavailable. Retain unsuccessful attempts. Run baseline/candidate once, then repeat critical unknown-effect, drift, permission and consumer cases in fresh sessions as the acceptance experiment requires; do not rerun until a lucky pass.

## Controlled provider run

A live mutation requires a separately authorized run-owned canary target, environment, exact effects and cleanup. Credentials alone do not provide that scope. Through the installed public tools, establish fresh identity/revision, apply the one authorized change, verify receipt and saved readback, and publish/read back only when requested and supported. Preserve pending receipts across restart and reconcile unknown effects; a new operation ID is not a safe retry.

Prove data and render only where relevant. Use bounded preview with authorized fields for data and read-only Browser inspection for visible changes. A correct save with a blank chart or wrong selector width remains a visual failure. Restore/cleanup only within the agreed canary scope and verify it; record unresolved effects instead of claiming rollback.

Without an available host or authorized canary, finish local validation and mark those levels `blocked` or `not_run` with the specific boundary. Package, component, host, provider mutation and render/business acceptance are separate claims.
