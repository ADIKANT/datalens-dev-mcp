function getPreparedLoadedData(loadedData, sourceName) {
  const sourceData = loadedData[sourceName];
  if (!sourceData) return [];

  const meta = sourceData.find((item) => item.event === 'metadata');
  const columnNames = meta?.data?.names || [];

  return sourceData
    .filter((item) => item.event === 'row')
    .map((rowItem) => {
      const obj = {};
      rowItem.data.forEach((field, idx) => {
        obj[columnNames[idx]] = field;
      });
      return obj;
    });
}

function formatInteger(value) {
  const rounded = Math.round(Number(value) || 0);
  const sign = rounded < 0 ? '-' : '';
  const abs = String(Math.abs(rounded));
  return `${sign}${abs.replace(/\B(?=(\d{3})+(?!\d))/g, ' ')}`;
}

function formatPercent(value) {
  if (value === null || value === undefined || !Number.isFinite(value)) return 'n/a';
  return `${value.toFixed(Math.abs(value) >= 10 ? 0 : 1).replace(/\.0$/, '')}%`;
}

function getDelta(currentValue, previousValue) {
  const diff = currentValue - previousValue;
  const pct = previousValue === 0 ? null : (diff / previousValue) * 100;
  return {
    diff,
    pct,
    tone: diff > 0 ? 'ok' : diff < 0 ? 'critical' : 'neutral',
  };
}

function buildSparklineGeometry(series, width, height, padding) {
  if (!series.length) {
    return {linePoints: '', areaPoints: ''};
  }

  const innerWidth = Math.max(1, width - padding * 2);
  const innerHeight = Math.max(1, height - padding * 2);
  const values = series.map((item) => Number(item.metric_value || 0));
  const maxValue = Math.max(...values, 0);
  const span = Math.max(1, maxValue);

  const pointList = series.map((item, idx) => {
    const x = padding + (series.length === 1 ? innerWidth / 2 : (idx / (series.length - 1)) * innerWidth);
    const y = padding + innerHeight - (Number(item.metric_value || 0) / span) * innerHeight;
    return {x, y};
  });

  const linePoints = pointList.map((point) => `${point.x},${point.y}`).join(' ');
  const baselineY = padding + innerHeight;
  const areaPoints = `${pointList[0].x},${baselineY} ${linePoints} ${pointList[pointList.length - 1].x},${baselineY}`;

  return {linePoints, areaPoints};
}

const summary = getPreparedLoadedData(Editor.getLoadedData(), 'metricSummary')[0] || {};
const trendRows = getPreparedLoadedData(Editor.getLoadedData(), 'metricTrend');

const currentValue = Number(summary.current_value || 0);
const previousValue = Number(summary.previous_value || 0);
const delta = getDelta(currentValue, previousValue);

module.exports = {
  render: Editor.wrapFn({
    args: [{
      title: summary.metric_title || 'Metric title',
      helpText: summary.help_text || 'Explain the metric here.',
      helpSource: summary.help_source || 'Source: describe the metric source.',
      currentValue,
      previousValue,
      delta,
      trendRows,
    }],
    fn: function(options, data) {
      function formatIntegerLocal(value) {
        const rounded = Math.round(Number(value) || 0);
        const sign = rounded < 0 ? '-' : '';
        const abs = String(Math.abs(rounded));
        return `${sign}${abs.replace(/\B(?=(\d{3})+(?!\d))/g, ' ')}`;
      }
      function formatPercentLocal(value) {
        if (value === null || value === undefined || !Number.isFinite(value)) return 'n/a';
        return `${value.toFixed(Math.abs(value) >= 10 ? 0 : 1).replace(/\.0$/, '')}%`;
      }
      function buildSparklineGeometryLocal(series, width, height, padding) {
        if (!series.length) {
          return {linePoints: '', areaPoints: ''};
        }

        const innerWidth = Math.max(1, width - padding * 2);
        const innerHeight = Math.max(1, height - padding * 2);
        const values = series.map((item) => Number(item.metric_value || 0));
        const maxValue = Math.max(...values, 0);
        const span = Math.max(1, maxValue);

        const pointList = series.map((item, idx) => {
          const x = padding + (series.length === 1 ? innerWidth / 2 : (idx / (series.length - 1)) * innerWidth);
          const y = padding + innerHeight - (Number(item.metric_value || 0) / span) * innerHeight;
          return {x, y};
        });

        const linePoints = pointList.map((point) => `${point.x},${point.y}`).join(' ');
        const baselineY = padding + innerHeight;
        const areaPoints = `${pointList[0].x},${baselineY} ${linePoints} ${pointList[pointList.length - 1].x},${baselineY}`;
        return {linePoints, areaPoints};
      }

      const rawWidth = Number(options?.width) || 0;
      const rawHeight = Number(options?.height) || 0;
      const width = rawWidth > 0 ? rawWidth : 420;
      const height = rawHeight > 0 ? rawHeight : 220;
      const denseMode = width < 380 || height < 190;
      const paddingX = denseMode ? 14 : 18;
      const paddingY = denseMode ? 14 : 18;
      const sparklineHeight = denseMode ? 44 : 58;
      const sparklineWidth = Math.max(120, width - paddingX * 2);
      const sparkline = buildSparklineGeometryLocal(data.trendRows, sparklineWidth, sparklineHeight, 4);
      const deltaColor = data.delta.tone === 'ok' ? '#0B8043' : data.delta.tone === 'critical' ? '#B3261E' : '#5F6368';
      const deltaBg = data.delta.tone === 'ok' ? '#E6F4EA' : data.delta.tone === 'critical' ? '#FDECEC' : '#F3F4F6';
      const titleFontSize = denseMode ? 18 : 20;

      return Editor.generateHtml(`
        <div style="box-sizing:border-box;width:100%;height:100%;padding:${paddingY}px ${paddingX}px;background:#FFFFFF;border:none;box-shadow:none;font-family:Inter, Arial, sans-serif;color:#111827;">
          <div style="display:flex;align-items:flex-start;justify-content:space-between;gap:12px;flex-wrap:wrap;">
            <div style="display:flex;align-items:center;gap:8px;">
              <div style="font-size:${titleFontSize}px;line-height:${titleFontSize + 2}px;font-weight:800;letter-spacing:0.08em;text-transform:uppercase;color:#5F6368;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">${data.title}</div>
              <dl-tooltip
                data-tooltip-content='${JSON.stringify(Editor.generateHtml(`<div style="max-width:260px;color:#111827;"><div style="font-weight:800;margin-bottom:6px;">${data.title}</div><div style="font-size:12px;line-height:1.35;">${data.helpText}</div><div style="margin-top:6px;font-size:12px;line-height:1.35;color:#667085;">${data.helpSource}</div></div>`))}'
                data-tooltip-placement='top'
                style="display:inline-flex;align-items:center;justify-content:center;width:18px;height:18px;border:none;border-radius:999px;background:#F2F4F7;color:#667085;font-size:12px;line-height:1;font-weight:800;"
              >?</dl-tooltip>
            </div>
            <div style="display:inline-flex;align-items:center;gap:8px;color:#667085;font-size:12px;line-height:1.35;font-weight:500;">
              <span>Source: demo rows</span>
              <span style="color:#98A2B3;">•</span>
              <span>Freshness: static example</span>
            </div>
          </div>
          <div style="margin-top:${denseMode ? 12 : 14}px;display:flex;align-items:flex-end;justify-content:space-between;gap:12px;flex-wrap:wrap;">
            <div style="font-size:${denseMode ? 28 : 36}px;line-height:1;font-weight:800;letter-spacing:-0.03em;color:#111827;">${formatIntegerLocal(data.currentValue)}</div>
            <div style="display:inline-flex;align-items:center;gap:8px;flex-wrap:wrap;">
              <div style="padding:${denseMode ? '4px 8px' : '6px 10px'};border-radius:999px;background:${deltaBg};color:${deltaColor};font-size:${denseMode ? 12 : 13}px;line-height:1.25;font-weight:700;">${formatPercentLocal(data.delta.pct)}</div>
              <div style="font-size:${denseMode ? 11 : 12}px;line-height:1.25;font-weight:700;letter-spacing:0.04em;color:#667085;text-transform:uppercase;">VS PREVIOUS PERIOD</div>
            </div>
          </div>
          <div style="margin-top:${denseMode ? 12 : 14}px;">
            <svg width="${sparklineWidth}" height="${sparklineHeight}" viewBox="0 0 ${sparklineWidth} ${sparklineHeight}" style="display:block;overflow:hidden;">
              <polyline fill="rgba(43, 117, 226, 0.12)" stroke="none" points="${sparkline.areaPoints}" />
              <polyline fill="none" stroke="#2B75E2" stroke-width="${denseMode ? 2 : 2.5}" stroke-linecap="round" stroke-linejoin="round" points="${sparkline.linePoints}" />
            </svg>
          </div>
        </div>
      `);
    }
  })
};
