// @cookbook-locale ru В production подключите dataset и сохраните выходные aliases.
// @cookbook-locale en In production bind the dataset and preserve output aliases.
// Fixture only: production generation replaces this SQL with a caller-owned dataset binding.
// Keep current_value/comparator_value/sparkline aliases stable in the production Sources tab.
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
