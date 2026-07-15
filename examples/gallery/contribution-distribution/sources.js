module.exports = {
  contributionRows: {
    qlConnectionId: Editor.getId('defaultConnection'),
    data: {
      sql_query: `
        SELECT '2026-W01' AS bucket_label, 'Organic' AS category_label, 42 AS metric_value
        UNION ALL SELECT '2026-W01', 'Paid', 28
        UNION ALL SELECT '2026-W01', 'Other', 10
        UNION ALL SELECT '2026-W02', 'Organic', 38
        UNION ALL SELECT '2026-W02', 'Paid', 34
        UNION ALL SELECT '2026-W02', 'Other', 8
      `,
    },
  },
};
