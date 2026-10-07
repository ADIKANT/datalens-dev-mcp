# Host evaluation and controlled live acceptance

The runtime uses direct typed `dl_*` tools and operation receipts. This repository has no runnable host-evaluation or live-canary runner. Do not invoke removed scripts or represent fixtures as a completed provider run.

## Local versus observed behavior

Existing replacement tests guard bounded local contracts. `scripts/installed_smoke.py` checks the installed package, SDK admission, manifest routing, stdio and absence of files in an unrelated cwd. Neither proves that the host selected the right skill, completed a multi-object task, wrote to DataLens or rendered a dashboard correctly.

Choose the actual scenario affected by the diff: metadata edit, Dataset preservation, one Editor tab, Dashboard filter/layout, requested publication, or continuation after drift/unknown outcome. Run only the relevant existing guards. Do not add test files, wording/count checks or a general evaluator by default. Keep full logs locally; report outcome and the first meaningful failure. A passed count is technical CI output, not user acceptance.

For a safe reproducible comparison, use the same actual task and environment before/after. Record network reads, HTTP bytes and model-visible output separately; do not call bytes tokens. A paid host/model comparison or broad repeated evaluation requires an explicit request. No synthetic model or fake provider can replace missing live evidence.

## Controlled provider run

A live mutation requires an authorized run-owned target, environment, exact effects and cleanup. Credentials alone do not supply that scope. Through installed public tools, establish fresh identity/revision, make the authorized change, check untouched state and saved readback, and publish/read back only when requested and supported. Follow [authorized scope and delivery](../skills/datalens-dashboard/references/authorized-scope.md) for drift, unknown writes and permission boundaries.

Prove data and render where affected: bounded preview with the relevant fields, then read-only Browser inspection for visible changes. A correct save with a blank chart or wrong selector behavior remains a visual failure. Restore/cleanup only within the agreed scope and verify it.

Record the tested commit/build, actual task and observable result, limitations and cleanup in a few lines. Without an available host or authorized canary, finish code, local checks and PR, and name the unavailable live boundary separately. Do not compensate with more synthetic cases.

## Precise-change scenarios

Use the installed candidate tools and its matching skills; record the commit and
skill digest with each observed trajectory. Do not put the expected solution in
the model prompt. Reuse the existing host execution method where available;
static wording checks and deterministic handler tests are separate evidence.

| Task supplied to the agent | Observe independently |
| --- | --- |
| Add a chart to an established direct-SQL/JS-selector project | Uses the project's source route without an unjustified Dataset |
| Add a standard view to an existing shared metric model | Reuses the Dataset and native Wizard where appropriate |
| Change one hint; another client changes geometry after the first read | Re-reads/rebases the hint, preserves full state, saves without publishing |
| Continue after intermediate payment/funnel views were cancelled | Retains the latest two views and required detail columns |
| Count overlapping entity groups and compare unequal weighted groups | Keeps order/entity keys, union distinct and aggregate denominator semantics |
| Clear a date while a category is selected | Actual source query removes only the date, preserves category and tab scope |
| Continue an interrupted write with lost response | Uses original receipt/reconcile, no new effect or revived old requirements |
| Repair a rejected recipe argument | One informed correction from the returned contract, no guessed batch retries |
| Give a short final response | Keeps definition, verification boundary and unresolved remainder |

The source/filter/render scenario additionally needs an authorized run-owned
canary, a bounded real source, period selection and date clearing with category
preserved, a neighboring tab check, wide/420 px inspection, and exact cleanup.
Local mocks cannot close that boundary. If that environment is unavailable,
record the specific blocked stages, zero external writes and any owned residue;
continue the local qualification and PR without waiting for SSO or merge.
