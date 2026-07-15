// Data binding: replace the query and connection alias, keep output names stable.
module.exports = {
  rows: {
    qlConnectionId: Editor.getId('defaultConnection'),
    data: {
      sql_query: `
        SELECT
          'Completed' AS title,
          'completed_issues' AS metric,
          128 AS current_value,
          120 AS comparator_value,
          'target' AS comparator_label,
          'Completed issues in selected period' AS hint
      `,
    },
  },
};
