# KPI card template

Source basis: distilled from project-authored KPI validation patterns and reduced to
a reusable `editor_advanced` template.

Use for `kpi_value_only`, `kpi_value_delta`, `kpi_value_sparkline`, and
`kpi_value_delta_sparkline`. Keep no-data handling inside the card; do not add a
separate no-data chart family.

Delta variants require an explicit comparator such as target, plan, SLA,
threshold, benchmark, or another declared baseline. Plain KPI generation uses
`kpi_value_only` or `kpi_value_sparkline`.
