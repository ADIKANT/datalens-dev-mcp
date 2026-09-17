# Dataset and Wizard contracts

- A new typed Dataset draft has exactly this ownership shape (values below are synthetic):

  ```json
  {
    "object_type": "dataset",
    "client_ref": "events_dataset",
    "name": "Events dataset",
    "dataset": {
      "connection_id": "existing-connection-id",
      "source": {
        "alias": "Events",
        "source_type": "CH_SUBSELECT",
        "parameters": {
          "manual": true,
          "subsql": "SELECT 'North' AS region, 42 AS amount"
        }
      },
      "fields": [
        {
          "guid": "region-guid",
          "title": "Region",
          "kind": "dimension",
          "source": "region"
        },
        {
          "guid": "amount-guid",
          "title": "Amount",
          "kind": "measure",
          "source": "amount",
          "aggregation": "sum"
        }
      ]
    }
  }
  ```

  Keep `connection_id`, `source`, and `fields` inside `dataset`. Do not add `snapshot` to this typed form. Run `dl_editor_validate` on the batch before `dl_object_create`; static validity still does not prove provider acceptance.
- `dl_dataset_validate` defaults to local field/formula checks. For an existing Dataset, `provider=true` validates the exact current saved state without saving. Optional `refresh_source_ids` must be source IDs from that Dataset; this requests provider schema refresh without forcing field replacement. The compact result separates provider validation from persistence. Set `include_provider_state=true` only when the complete returned candidate is needed for an authorized, separately revision-guarded update. Never fabricate `raw_schema`, set validity flags, or clear component errors to hide a source failure. Validate SQL against the Dataset's actual connection, not another engine. Query preview and chart rendering remain separate checks.
- `dl_dataset_preview` accepts `columns` as a list of exact Dataset GUID strings; `fields` has a different method-specific role and is not a substitute. A short valid call is `dl_dataset_preview(dataset_id="synthetic-dataset-id", columns=["synthetic-amount-guid"])`. Multi-page reads require an explicit sort and unique tie-breaker; query success proves returned data only, not a saved or published chart. If a nested argument is rejected, correct it from the typed tool error before any provider request instead of guessing alternate payload shapes.
- Preserve an existing Dataset field GUID and meaning on update. A chart-local calculated field remains local unless the user explicitly requests a shared Dataset change.
- `Measure Names` and `Measure Values` are chart-generated technical fields. Neither can filter a chart. Do not invent Dataset GUIDs or source columns for them. `Measure Values` sorting is limited to the documented area/normalized-area case after `Measure Names` is placed in Colors.
- Do not combine LOD with `AGO` or `AT_DATE` in one visualization, even when they occur in different fields. Do not generalize that into a ban on every nested aggregation.
- For ratios such as average check, preserve business grain: prefer `SUM([revenue]) / SUM([orders])` with explicit zero-denominator behavior over an unreviewed average of row ratios.
- Compile new Wizard shapes with the pinned SDK. Current API v3 Wizard V1 uses `data.sources.datasetsIds`, `links`, `updates`, `filters` and `hierarchies`, with fields in visualization role slots. Read and preserve the actual full state before updating. Multi-dataset links map each dataset ID to its exact field GUID/title and dataset ID/name; matching display titles do not establish matching fields. Preserve chart-local updates, each measure's dataset binding, aliases and date filter semantics. Wizard get/update endpoints are experimental; successful save and exact published readback do not prove execution. If published rendering fails, compare saved/published state, bounded source previews and the same period in standalone/dashboard views before a minimal sandbox reproduction. Do not repeatedly resave equivalent payloads or remove business filters without new evidence.

- For an in-place Dataset change, read the saved object, retain the full nested `dataset` state and patch only requested fields through `dl_object_update`. Root `revId` and `dataset.revision_id` are different: retain both; never substitute one for the other. An explicitly returned null inner revision is preserved and compared against the fresh read; it requires the observed outer saved revision. A missing inner revision remains invalid. The adapter checks the fresh revisions and sends the nested revision to `updateDataset` API v3. SDK 3.0.0 raw replacement strips it, so this one route uses the existing direct provider adapter. `dl_method_schema("updateDataset")` returns operation/reference metadata and a synthetic example; it is not the complete provider payload JSON Schema.
- On conflict, read back the source IDs and changed content before deciding whether anything applied. Never replay an unchanged failed payload under another operation ID. A confirmed non-applied outcome permits a corrected in-scope request without another approval conversation.
- Dataset save readback excludes the documented provider-owned `sources[].parameter_hash`, which changes when source parameters change. It still checks authored parameters, fields and revision guards. The returned `dataset_validation` summarizes provider validity independently: a saved SQL change can coexist with stale/invalid source metadata and does not prove data readiness. Existing uncertain receipts remain unchanged until an explicit, evidence-based reconciliation.
- Summarize changes with paths, counts and source references; return complete source arrays only when requested. API-only source changes need update/readback checks, not a Browser render check. Read applicable local `reference_files` when a visual component is requested; those paths are not automatically interpreted as visual settings.

Before changing a formula or relative-date filter, read the exact field GUIDs and provider data types, validate the expression and preview the relevant values. A load-date-like name does not establish time semantics: `date` and `timestamp` are different. Resolve the supported relative-date syntax before saving, not afterward.

## Current source readiness

For upstream-dependent metrics, establish the contract in the connection actually used by the target. A repository column, merge, release promotion or green CI is implementation evidence, not proof of a changed physical source. Use addressed metadata and a small real query; report a missing query capability or denied access as unverified, not as an absent field.

| Evidence | Establish before depending on it |
| --- | --- |
| Physical source and connection | Current connection identity and source/query used by the Dataset or direct-source Editor |
| Fields | Physical names/types, current Dataset GUIDs and formulas, scalar versus array, business key versus display label |
| Freshness and missingness | Actual data dates/load timestamp and expected NULL, empty arrays, historical gaps and unresolved keys |
| Grain and units | Row key, booking/entity versus day or allocation, duration unit and aggregation; compare the requested totals |
| Filter binding | Exact bound field/parameter, selected values and NULL behavior; check totals before/after and affected UI |

For booking format and Insight-style driver dimensions, inspect their actual values and relationship to customers/teams. A multi-select label, user picker and object identifier can be different fields despite similar names. Resolve IDs through the declared key relationship; never pair two arrays by incidental order. Do not explode arrays or add many-to-many joins that duplicate hours or booking counts. Check the grain before/after the join or filter, including an actual NULL/empty case when available; name coverage gaps when no such case exists. A materially different metric definition, such as allocating one booking's hours among multiple drivers, requires the business rule rather than a cosmetic patch.

If only part of the source is ready, complete independent authorized UI/metadata changes and identify each dependent item and the evidence needed to unblock it. Do not substitute invented zeros, a temporary Dataset or another source with different semantics. Retain upstream errors as errors; a valid empty query is different from a missing source or an invalid KPI. The ready subset does not complete the whole request.
