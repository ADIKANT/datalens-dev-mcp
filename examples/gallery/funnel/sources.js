module.exports = {
  stageRows: {
    qlConnectionId: Editor.getId('defaultConnection'),
    data: {
      sql_query: `
        SELECT 1 AS stage_order, 'Reach' AS stage_label, 4200 AS metric_value
        UNION ALL SELECT 2, 'Visits', 2600
        UNION ALL SELECT 3, 'Qualified', 1680
        UNION ALL SELECT 4, 'Activated', 940
      `,
    },
  },
};
