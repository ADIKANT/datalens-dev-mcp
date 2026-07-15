const qlConnectionId = Editor.getId('defaultConnection');

module.exports = {
  segmentRows: {
    qlConnectionId,
    data: {
      sql_query: `
        SELECT 'Organic' AS category_label, 42 AS metric_value
        UNION ALL SELECT 'Paid', 28
        UNION ALL SELECT 'CRM', 18
        UNION ALL SELECT 'Other', 12
      `,
    },
  },
  treemapRows: {
    qlConnectionId,
    data: {
      sql_query: `
        SELECT 'All channels' AS parent_label, 'Organic' AS child_label, 42 AS metric_value
        UNION ALL SELECT 'All channels', 'Paid', 28
        UNION ALL SELECT 'All channels', 'CRM', 18
        UNION ALL SELECT 'All channels', 'Other', 12
      `,
    },
  },
};
