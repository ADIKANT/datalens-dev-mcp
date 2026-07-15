// Data binding: output bucket, metric, and value columns for the time renderer.
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
