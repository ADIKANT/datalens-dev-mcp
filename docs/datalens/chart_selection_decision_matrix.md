# Chart Selection Decision Matrix

This project-authored guide summarizes `config/datalens_chart_param_matrix.json`,
`config/datalens_chart_design_rules.json`, the route policy, and the official
DataLens visualization reference.

## Selection Process

1. Pick dashboard type and user role.
2. State business action and question.
3. Validate metric definition, grain, explicit comparator or target when needed, source freshness, required fields, and data quality risks.
4. Classify data shape: KPI/status, time, category/ranking, part-to-whole, distribution, relationship, geography, exact values, alerting, or experiment result.
5. Choose route from `config/route_selection_policy_v5.json`: standard charts
   use `wizard_native`; registered gaps use Editor; direct QL requests use
   `ql_explicit`.
6. Choose approved chart family and registered template.
7. Persist chart, metric, selector, and object relations before payload planning.
8. Ask a precise fallback question when critical evidence is missing.

## Decision Matrix

| Business question | Data shape | Dashboard type | Default family | Route | Required inputs |
| --- | --- | --- | --- | --- | --- |
| What is the current status? | single metric plus optional delta | overview, alerts | `kpi_value_only` / `kpi_value_delta` | `wizard_native` / `metric` | metric, period or freshness |
| Which categories rank highest or lowest? | category + measure | overview, analytical tool | `horizontal_bar` | `wizard_native` / `bar` | category, measure, sort |
| How does a measure change over time? | date + measure | overview, analytical tool | `line_chart` | `wizard_native` / `line` | date field, grain, measure |
| What is the distribution shape? | numeric measure | analytical tool | `histogram` or `box_plot` | `editor_advanced` | measure, bins/groups |
| Is there a relationship between measures? | two numeric measures | analytical tool | `scatter` | `wizard_native` / `scatter` | x measure, y measure, question |
| What share does each part contribute? | whole + parts | overview | `donut`, `treemap`, or bar alternative | `wizard_native` | whole definition, parts, small stable set |
| Where is the metric or status located? | geo field + measure/status | overview, object management | `native_map_geo_widget` | `wizard_native` / `geolayer` | geo evidence, measure/status |
| What exact values or objects need repeated action? | detail rows | self-service, object management | `table_node` | `wizard_native` / `flatTable` | fields, filters, sort |
| What needs attention now? | status/threshold | alerts | `bullet_assignees` or `table_node` | registered JS gap or `wizard_native` | explicit threshold, owner/action |

Examples live in `docs/datalens/model_response_examples.md`; machine-readable rules live in `config/datalens_chart_param_matrix.json`.
