const env = Editor.getParam('environment')?.[0] || 'dev';
const connectionName =
  env === 'prod' ? 'prodConnection' :
  env === 'stage' ? 'stageConnection' :
  'devConnection';

const qlConnectionId = Editor.getId(connectionName);

module.exports = {
  metricSummary: {
    qlConnectionId,
    data: {
      sql_query: `
        SELECT
          1842 AS current_value,
          1710 AS previous_value,
          'Active vehicles' AS metric_title,
          'Active vehicles in the selected period.' AS help_text,
          'Source: curated demo rows' AS help_source
      `,
    },
  },
  metricTrend: {
    qlConnectionId,
    data: {
      sql_query: `
        SELECT '2026-01-01' AS event_date, 1660 AS metric_value
        UNION ALL SELECT '2026-01-02', 1695
        UNION ALL SELECT '2026-01-03', 1710
        UNION ALL SELECT '2026-01-04', 1768
        UNION ALL SELECT '2026-01-05', 1789
        UNION ALL SELECT '2026-01-06', 1814
        UNION ALL SELECT '2026-01-07', 1842
      `,
    },
  },
};
