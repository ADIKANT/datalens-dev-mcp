const {formatCompact, safeId, toNumber, toStringValue} = require('./chart-data-utils');

function normalizeFunnelStages(rows) {
  return [...rows]
    .sort((left, right) => toNumber(left.stage_order) - toNumber(right.stage_order))
    .map((row, index, all) => {
      const value = toNumber(row.metric_value);
      const first = toNumber(all[0]?.metric_value, value || 1) || 1;
      return {
        id: safeId(row.stage_label || index),
        stageLabel: toStringValue(row.stage_label, `Stage ${index + 1}`),
        label: toStringValue(row.stage_label, `Stage ${index + 1}`),
        metricValue: value,
        value,
        conversionRate: (value / first) * 100,
      };
    });
}

function buildFunnelTooltipItems(stages) {
  return stages.map((stage) => ({
    id: stage.id,
    title: stage.stageLabel || stage.label,
    rows: [
      {label: 'Value', value: formatCompact(stage.metricValue || stage.value)},
      {label: 'Conversion', value: `${Math.round(stage.conversionRate || 0)}%`},
    ],
  }));
}

function renderFunnelStageBars(stages) {
  const maxValue = Math.max(1, ...stages.map((stage) => Number(stage.metricValue || stage.value) || 0));
  return stages.map((stage, index) => `<div data-id="${stage.id}" style="height:28px;margin:6px auto;background:#2B75E2;opacity:${1 - index * 0.08};width:${Math.max(12, ((stage.metricValue || stage.value) / maxValue) * 100)}%;color:#fff;display:flex;align-items:center;justify-content:center;font-size:12px;font-weight:800;">${stage.label || stage.stageLabel}</div>`).join('');
}

module.exports = {buildFunnelTooltipItems, normalizeFunnelStages, renderFunnelStageBars};
