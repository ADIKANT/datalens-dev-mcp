/**
 * Required edit point: connect your source and preserve the documented output aliases.
 * Route: editor_advanced. Technical parameter names and aliases are language-neutral.
 */
// Parameterized ClickHouse template with filtering and pre-aggregation.
const params = Editor.getParams ? (Editor.getParams() || {}) : {};
function sqlLiteral(value) {
  return "'" + String(value == null ? '' : value).split("'").join("''") + "'";
}
const dateFrom = sqlLiteral((params.dateFrom || ['2026-01-01'])[0]);
const dateTo = sqlLiteral((params.dateTo || ['2026-01-30'])[0]);
const allowedSteps = new Set(['auto', 'day', 'week', 'month']);
const requestedStep = String((params.timeStep || ['auto'])[0]);
const timeStep = allowedSteps.has(requestedStep) ? requestedStep : 'auto';
const sqlQuery = `
  SELECT
    category_name AS label,
    series_name AS group,
    sum(metric_value) AS value,
    sum(target_value) AS target
  FROM __TABLE__
  WHERE event_date BETWEEN toDate(${dateFrom}) AND toDate(${dateTo})
  GROUP BY label, group, target
  ORDER BY 1
  /* timeStep=${timeStep}; replace __TABLE__ and the generic source columns */
`;
module.exports = {
  rows: {qlConnectionId: Editor.getId('defaultConnection'), data: {sql_query: sqlQuery}},
};
