# DQ Reconciliation Workflow

Use this workflow when a dashboard value must be reconciled against a control
baseline without committing raw control files.

## Steps

1. Record only an aggregate control-file summary with
   `dl_ingest_dq_control_summary`.
2. Build a layer plan with `dl_build_dq_layer_reconciliation_plan`.
3. Probe layers through a read-only metadata/data evidence provider.
4. Classify sanitized records with `dl_classify_dq_reconciliation`.
5. Build a before/after report with `dl_build_dq_before_after_report` before
   dashboard-side fixes.

## Layer Model

The default plan follows:

- control baseline
- raw source presence
- history layer
- current layer
- mart layer
- dashboard reproduction

Identity must separate the strict business key from the stable RK/resolved key.
Mutable order numbers or similar business keys can change; the stable key is
the bridge for renumbering analysis.

## Buckets

- `ok_exact_dm`
- `ok_rk_renumbered`
- `source_status_conflict`
- `missing_raw`
- `missing_current_edm_order`
- `missing_edm_item_amount`
- `missing_dm_amount`
- `dashboard_logic_issue`
- `extra_dashboard_row`

## Guards

The bridge report reconciles baseline amount/count to dashboard reproduction
amount/count. Dashboard-only fixes are blocked when upstream evidence lands in
source or layer-missing buckets. Do not change dashboard logic merely to match a
control file when read-only layer evidence contradicts the control baseline.

Raw control rows, credential material, auth headers, cookies, and token-like
values must not be written to repo artifacts.
