// @cookbook-locale ru В production подключите dataset и сохраните выходные aliases.
// @cookbook-locale en In production bind the dataset and preserve output aliases.
// Fixture only: production generation replaces this SQL with a caller-owned dataset binding.
// Keep bucket/metric/value aliases stable in the production Sources tab.
module.exports = {
  rows: {
    qlConnectionId: Editor.getId('defaultConnection'),
    data: {
      sql_query: `
        SELECT '2026-W01' AS bucket, 'Created' AS metric, 42 AS value
        UNION ALL SELECT '2026-W01', 'Completed', 36
        UNION ALL SELECT '2026-W02', 'Created', 48
        UNION ALL SELECT '2026-W02', 'Completed', 41
      `,
    },
  },
};
