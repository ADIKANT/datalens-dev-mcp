# Object Relations

Record dashboard, selector, chart, dataset, connector, and field relations.

Required relation columns:

| Selector | Target chart | Dataset | Fields | Native title/hint | Status |
| --- | --- | --- | --- | --- | --- |
| `<SELECTOR_PARAM>` | `<CHART_KEY>` | `<DATASET_ID>` | `<FIELD_LIST>` | `<NATIVE_TITLE>` / `<NATIVE_HINT>` | `planned_placeholder` |

Selectors must declare target widgets before implementation. Use placeholders
for source object ids unless the user explicitly chooses local-only project
state.
