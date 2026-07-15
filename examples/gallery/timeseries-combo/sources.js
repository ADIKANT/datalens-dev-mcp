const qlConnectionId = Editor.getId('defaultConnection');

module.exports = {
  lineRows: {
    qlConnectionId,
    data: {
      sql_query: `
        SELECT '2026-01-01' AS period_label, 'Primary' AS series_label, 22 AS metric_value
        UNION ALL SELECT '2026-01-02', 'Primary', 26
        UNION ALL SELECT '2026-01-03', 'Primary', 24
        UNION ALL SELECT '2026-01-04', 'Primary', 29
        UNION ALL SELECT '2026-01-05', 'Primary', 31
        UNION ALL SELECT '2026-01-06', 'Primary', 28
      `,
    },
  },
  bucketRows: {
    qlConnectionId,
    data: {
      sql_query: `
        SELECT 'W1' AS period_label, 21 AS metric_value
        UNION ALL SELECT 'W2', 26
        UNION ALL SELECT 'W3', 29
        UNION ALL SELECT 'W4', 24
      `,
    },
  },
  comboBarRows: {
    qlConnectionId,
    data: {
      sql_query: `
        SELECT '2026-01-01' AS period_label, 18 AS metric_value
        UNION ALL SELECT '2026-01-08', 25
        UNION ALL SELECT '2026-01-15', 23
        UNION ALL SELECT '2026-01-22', 31
        UNION ALL SELECT '2026-01-29', 28
      `,
    },
  },
  comboLineRows: {
    qlConnectionId,
    data: {
      sql_query: `
        SELECT '2026-01-01' AS period_label, 62 AS metric_value
        UNION ALL SELECT '2026-01-08', 66
        UNION ALL SELECT '2026-01-15', 71
        UNION ALL SELECT '2026-01-22', 74
        UNION ALL SELECT '2026-01-29', 79
      `,
    },
  },
  funnelStageRows: {
    qlConnectionId,
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
