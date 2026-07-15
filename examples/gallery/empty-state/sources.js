const env = Editor.getParam('environment')?.[0] || 'dev';
const connectionName =
  env === 'prod' ? 'prodConnection' :
  env === 'stage' ? 'stageConnection' :
  'devConnection';

const qlConnectionId = Editor.getId(connectionName);

module.exports = {
  mainSeries: {
    qlConnectionId,
    data: {
      sql_query: `
        SELECT
          event_date AS x,
          metric_value AS y
        FROM analytics.metric_daily
        WHERE event_date BETWEEN toDate({{date_from}}) AND toDate({{date_to}})
        ORDER BY event_date
      `,
    },
  },
};
