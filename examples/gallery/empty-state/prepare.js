const rows = Editor.getLoadedData('mainSeries') || [];

const series = rows.map((row) => ({
  id: String(row.x),
  x: row.x,
  y: Number(row.y || 0),
}));

const status = rows.length ? 'ok' : 'unavailable';

module.exports = {
  status,
  series,
  render: Editor.wrapFn({
    args: [{status, series}],
    fn: function(options, payload) {
      if (payload.status !== 'ok') {
      return Editor.generateHtml(`<div class="empty-state" data-state="${payload.status}">NO DATA</div>`);
    }

      return Editor.generateHtml(
        `<div class="chart-root" data-points="${payload.series.length}"></div>`,
      );
    },
  }),
};
