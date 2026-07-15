const qlConnectionId = Editor.getId('defaultConnection');
const selectedMetric = Editor.getParam('selected_metric')?.[0] || 'orders';

module.exports = {
  compareSeries: {
    qlConnectionId,
    data: {
      sql_query: `
        SELECT
          period_label,
          ${selectedMetric} AS metric_value,
          target_value
        FROM analytics.metric_compare
        ORDER BY sort_order
      `,
    },
  },
};
