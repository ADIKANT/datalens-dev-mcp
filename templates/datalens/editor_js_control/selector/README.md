# Selector template

The compiler materializes each registered family from an explicit
`selector_contract`:

- single, multi, search, and static selects consume a caller-owned parameter,
  labelled string options, defaults, and reset behavior;
- date ranges use the official `range-datepicker` contract with either one
  interval `param` or the paired `param_from` / `param_to` form;
- dynamic selectors require dataset output alias `value`, accept optional
  `title`, and normalize DataLens event-stream rows.

Production generation blocks missing static options or missing dynamic source
bindings. It never invents a `segment` parameter or option values. Every value
emitted on the DataLens Params tab is an array of strings. Legacy `param` /
`options` inputs remain available only when a caller supplies them explicitly;
the static golden fixture path is the only path that reads example inputs.

Multi-control rows keep left labels and percentage widths with a 94 percent row
budget.
