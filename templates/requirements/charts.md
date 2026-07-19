# Charts

Record planned and implemented charts.

Required catalog columns:

| Chart | Route | Dataset | Metrics | Dimensions | Filters | Selectors | Native title | Native hint | Source requirement | Status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `<CHART_KEY>` | `<ROUTE>` | `<DATASET_ID>` | `<METRIC_NAME>` | `<DIMENSION_FIELD>` | `<FILTER_FIELD>` | `<SELECTOR_PARAM>` | `<NATIVE_TITLE>` | `<NATIVE_HINT>` | `<SOURCE_REQUIREMENT>` | `planned` |

Use placeholders until the user explicitly chooses local-only project state or
live readback supplies real ids.

For every chart also record:

- business question, decision/action, metric formula, unit, grain, and cumulative window;
- explicit comparator and the exact selected/comparison interval tooltip contract;
- missing/zero/future policy (`N/A`, observed zero, preserved gaps, no future zero-fill);
- date and number formats (`DD.MM.YY`, `MM.YY`, locale grouping, nice unique ticks);
- business hint content: meaning, calculation, and limitations, without rendering instructions;
- layout owner, content-height profile, and responsive behavior;
- source availability state: `ABSENT`, `PRESENT_EMPTY`, or `PRESENT_WITH_DATA`.
