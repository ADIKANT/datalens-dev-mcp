# Selectors

Record selector names, parameters, options, defaults, widths, and affected
widgets.

| Selector | Role | Parameter/field | Default | Width | Affected tabs/objects | Update behavior |
| --- | --- | --- | --- | --- | --- | --- |
| `<CONTROL_KEY>` | `<PERIOD_COMPARISON_GRAIN_FILTER>` | `<PARAM_OR_FIELD>` | `<EMPTY_MEANS_ALL_OR_VALUE>` | `<PERCENT>` | `<EXPLICIT_IDS>` | `<MANUAL_OR_EXPLICIT>` |

Rules:

- selector rows use left labels and total at most 94 percent;
- one calendar Period control owns the selected interval;
- Comparison is separate, contextual to Period, and falls back only to a valid option;
- empty selection means all when the business contract allows it; do not invent a magic `All` value;
- controls do not mutate parameters during recalculation and defaults live only in initial/reset state;
- automatic apply/update is off unless the accepted requirements explicitly need it.
