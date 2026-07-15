const rows = Editor.getLoadedData('compareSeries') || [];
const compareMode = Editor.getParam('compare_mode')?.[0] || 'none';

module.exports = {
  compareMode,
  series: rows.map((row) => ({
    label: row.period_label,
    value: Number(row.metric_value || 0),
    target: Number(row.target_value || 0),
  })),
  render: Editor.wrapFn({
    args: [{
      series: rows.map((row) => ({
        label: row.period_label,
        value: Number(row.metric_value || 0),
        target: Number(row.target_value || 0),
      })),
    }],
    fn: function(options, payload) {
      return Editor.generateHtml(
        `<div class="chart-root" data-series-count="${payload.series.length}"></div>`,
      );
    },
  }),
};
