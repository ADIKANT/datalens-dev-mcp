# Dataset and Wizard contracts

- `dl_dataset_validate` checks identity and known formula interactions. It does not replace provider validation or prove connector-specific function support.
- `dl_dataset_preview` accepts exact Dataset GUIDs. Multi-page reads require an explicit sort and unique tie-breaker; query success proves returned data only, not a saved or published chart.
- Preserve an existing Dataset field GUID and meaning on update. A chart-local calculated field remains local unless the user explicitly requests a shared Dataset change.
- `Measure Names` and `Measure Values` are chart-generated technical fields. Neither can filter a chart. Do not invent Dataset GUIDs or source columns for them. `Measure Values` sorting is limited to the documented area/normalized-area case after `Measure Names` is placed in Colors.
- Do not combine LOD with `AGO` or `AT_DATE` in one visualization, even when they occur in different fields. Do not generalize that into a ban on every nested aggregation.
- For ratios such as average check, preserve business grain: prefer `SUM([revenue]) / SUM([orders])` with explicit zero-denominator behavior over an unreviewed average of row ratios.
- Compile new Wizard shapes with the pinned SDK. Before updating an existing Wizard, inspect its current `datasetsPartialFields` shape and preserve that version-specific structure.
