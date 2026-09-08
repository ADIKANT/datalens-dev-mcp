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
- `dl_dataset_validate` checks identity and known formula interactions. It does not replace provider validation or prove connector-specific function support.
- `dl_dataset_preview` accepts exact Dataset GUIDs. Multi-page reads require an explicit sort and unique tie-breaker; query success proves returned data only, not a saved or published chart.
- Preserve an existing Dataset field GUID and meaning on update. A chart-local calculated field remains local unless the user explicitly requests a shared Dataset change.
- `Measure Names` and `Measure Values` are chart-generated technical fields. Neither can filter a chart. Do not invent Dataset GUIDs or source columns for them. `Measure Values` sorting is limited to the documented area/normalized-area case after `Measure Names` is placed in Colors.
- Do not combine LOD with `AGO` or `AT_DATE` in one visualization, even when they occur in different fields. Do not generalize that into a ban on every nested aggregation.
- For ratios such as average check, preserve business grain: prefer `SUM([revenue]) / SUM([orders])` with explicit zero-denominator behavior over an unreviewed average of row ratios.
- Compile new Wizard shapes with the pinned SDK. Before updating an existing Wizard, inspect its current `datasetsPartialFields` shape and preserve that version-specific structure.

- For an in-place Dataset change, read the saved object, retain the full nested `dataset` state and patch only requested fields through `dl_object_update`. Root `revId` and `dataset.revision_id` are different: retain both; never substitute one for the other. The adapter checks the fresh revisions and sends the nested revision to `updateDataset` v2. SDK 0.9.0 raw replacement strips it, so this one route uses the existing direct provider adapter. `dl_method_schema("updateDataset")` returns a reference contract and synthetic example, not a full JSON Schema.
- On conflict, read back the source IDs and changed content before deciding whether anything applied. Never replay an unchanged failed payload under another operation ID. A confirmed non-applied outcome permits a corrected in-scope request without another approval conversation.
- Summarize changes with paths, counts and source references; return complete source arrays only when requested. API-only source changes need update/readback checks, not a Browser render check. Read applicable local `reference_files` when a visual component is requested; those paths are not automatically interpreted as visual settings.
