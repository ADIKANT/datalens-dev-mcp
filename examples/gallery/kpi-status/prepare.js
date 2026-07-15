const {renderAdvancedFrame} = require('../../../templates/advanced/chart-shell');
const {
  formatCompact,
  formatPercent,
  getParamScalar,
  getSourceRows,
  safeId,
  toNumber,
  toStringValue,
} = require('../../../templates/advanced/chart-data-utils');
const {renderSourceFreshness} = require('../../../templates/advanced/source-freshness');
const {renderTooltipShell} = require('../../../templates/advanced/tooltip');
const {HOUSE_STYLE} = require('../../../templates/advanced/style-tokens');
const {linearScale} = require('../../../templates/advanced/chart-svg-utils');

const REQUESTED_VARIANT = getParamScalar('card_variant', 'kpi_value_delta_sparkline');
const SUPPORTED_VARIANTS = new Set([
  'kpi_value_only',
  'kpi_value_delta',
  'kpi_value_sparkline',
  'kpi_value_delta_sparkline',
]);
const VARIANT = SUPPORTED_VARIANTS.has(REQUESTED_VARIANT) ? REQUESTED_VARIANT : 'kpi_value_delta_sparkline';
const SPARKLINE_VARIANTS = new Set(['kpi_value_sparkline', 'kpi_value_delta_sparkline']);
const DELTA_VARIANTS = new Set(['kpi_value_delta', 'kpi_value_delta_sparkline']);

function hasSourceLoaded(name) {
  const direct = Editor.getLoadedData(name);
  if (direct !== undefined && direct !== null) {
    return true;
  }
  const loaded = Editor.getLoadedData() || {};
  return Object.prototype.hasOwnProperty.call(loaded, name);
}

function getStateAppearance(state) {
  const normalized = toStringValue(state, 'neutral').trim().toLowerCase();
  if (normalized === 'ok') {
    return {
      state: 'ok',
      fg: HOUSE_STYLE.colors.semantic.ok,
      bg: '#E6F4EA',
      label: 'On track',
    };
  }
  if (normalized === 'warning') {
    return {
      state: 'warning',
      fg: HOUSE_STYLE.colors.semantic.warning,
      bg: '#FFF4E5',
      label: 'Watch',
    };
  }
  if (normalized === 'critical') {
    return {
      state: 'critical',
      fg: HOUSE_STYLE.colors.semantic.critical,
      bg: '#FDF2F2',
      label: 'Action needed',
    };
  }
  if (normalized === 'unavailable') {
    return {
      state: 'unavailable',
      fg: HOUSE_STYLE.colors.semantic.unavailable,
      bg: '#F3F4F6',
      label: 'Unavailable',
    };
  }
  return {
    state: 'neutral',
    fg: HOUSE_STYLE.colors.semantic.neutral,
    bg: '#F3F4F6',
    label: 'Stable',
  };
}

function buildSparkline(points, width, height) {
  if (points.length < 2) {
    return '';
  }

  const padding = 6;
  const xStep = (width - padding * 2) / Math.max(1, points.length - 1);
  const min = Math.min(...points.map((point) => point.value));
  const max = Math.max(...points.map((point) => point.value));
  const yScale = linearScale(min, max === min ? max + 1 : max, height - padding, padding);
  const linePoints = points.map((point, index) => ({
    x: padding + index * xStep,
    y: yScale(point.value),
    id: point.id,
  }));

  const areaPoints = [
    `${linePoints[0].x},${height - padding}`,
    ...linePoints.map((point) => `${point.x},${point.y}`),
    `${linePoints[linePoints.length - 1].x},${height - padding}`,
  ].join(' ');

  return `
    <svg width="${width}" height="${height}" viewBox="0 0 ${width} ${height}" style="display:block;overflow:visible;">
      <polyline fill="rgba(43, 117, 226, 0.14)" stroke="none" points="${areaPoints}"></polyline>
      <polyline fill="none" stroke="${HOUSE_STYLE.colors.data.primary}" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" points="${linePoints.map((point) => `${point.x},${point.y}`).join(' ')}"></polyline>
      ${linePoints.map((point, index) => {
        const radius = index === linePoints.length - 1 ? 4 : 3;
        return `<circle data-id="${point.id}" cx="${point.x}" cy="${point.y}" r="${radius}" fill="${HOUSE_STYLE.colors.data.primary}" stroke="${HOUSE_STYLE.colors.surface.base}" stroke-width="1.5"></circle>`;
      }).join('')}
    </svg>
  `;
}

function buildCardModel() {
  const summaryLoaded = hasSourceLoaded('metricSummary');
  const sparklineLoaded = hasSourceLoaded('sparklineSeries');

  if (!summaryLoaded) {
    return {
      cardVariant: VARIANT,
      title: 'KPI Card',
      helpBody: 'The summary source is unavailable in the active environment.',
      helpSource: 'datalens-advanced-editor KPI family asset',
      status: 'unavailable',
      tooltipItems: [],
      freshnessHtml: '',
    };
  }

  const summary = getSourceRows('metricSummary')[0];
  if (!summary) {
    return {
      cardVariant: VARIANT,
      title: 'KPI Card',
      helpBody: 'No summary rows were returned for the active KPI card.',
      helpSource: 'datalens-advanced-editor KPI family asset',
      status: 'empty',
      tooltipItems: [],
      freshnessHtml: '',
    };
  }

  if (SPARKLINE_VARIANTS.has(VARIANT) && !sparklineLoaded) {
    return {
      cardVariant: VARIANT,
      title: toStringValue(summary.metric_title, 'KPI Card'),
      helpBody: toStringValue(summary.help_text, 'The sparkline source is unavailable in the active environment.'),
      helpSource: toStringValue(summary.help_source, 'datalens-advanced-editor KPI family asset'),
      status: 'unavailable',
      tooltipItems: [],
      freshnessHtml: renderSourceFreshness({
        sourceLabel: toStringValue(summary.source_label),
        freshnessLabel: toStringValue(summary.freshness_label),
        updatedAt: toStringValue(summary.updated_at),
      }),
    };
  }

  const currentValue = toNumber(summary.current_value);
  const previousValue = toNumber(summary.previous_value);
  const targetValue = toNumber(summary.target_value);
  const deltaValue = currentValue - previousValue;
  const deltaPercent = previousValue !== 0 ? (deltaValue / previousValue) * 100 : 0;
  const stateAppearance = getStateAppearance(toStringValue(summary.state, 'neutral'));

  const sparkline = SPARKLINE_VARIANTS.has(VARIANT)
    ? getSourceRows('sparklineSeries').map((row, index) => ({
        id: safeId(`${row.event_date}_${index}`),
        label: toStringValue(row.event_date),
        value: toNumber(row.metric_value),
      }))
    : [];

  return {
    cardVariant: VARIANT,
    title: toStringValue(summary.metric_title, 'KPI Card'),
    helpBody: toStringValue(summary.help_text, 'Explain the metric semantics and why it matters here.'),
    helpSource: toStringValue(summary.help_source, 'datalens-advanced-editor KPI family asset'),
    status: stateAppearance.state === 'unavailable' ? 'unavailable' : 'ok',
    valueLabel: formatCompact(currentValue),
    currentValue,
    previousValue,
    targetValue,
    deltaValue,
    deltaPercent,
    comparisonLabel: toStringValue(summary.comparison_label, 'Vs previous period'),
    noteText: toStringValue(summary.note_text),
    stateAppearance,
    stateLabel: toStringValue(summary.state_label, stateAppearance.label),
    freshnessHtml: renderSourceFreshness({
      sourceLabel: toStringValue(summary.source_label),
      freshnessLabel: toStringValue(summary.freshness_label),
      updatedAt: toStringValue(summary.updated_at),
    }),
    sparkline,
    tooltipItems: sparkline.map((point) => ({
      id: point.id,
      title: point.label,
      rows: [{label: 'Value', value: formatCompact(point.value)}],
    })),
  };
}

function renderCardBody(model, width, height, compactnessMode) {
  const showDelta = DELTA_VARIANTS.has(model.cardVariant);
  const showSparkline = SPARKLINE_VARIANTS.has(model.cardVariant) && model.sparkline.length >= 2;
  const valueSize = compactnessMode === 'dense' ? 30 : compactnessMode === 'compact' ? 38 : 46;
  const helperSize = compactnessMode === 'dense' ? 11 : 12;
  const sparklineHeight = compactnessMode === 'dense' ? 58 : 72;
  const sparklineHtml = showSparkline ? buildSparkline(model.sparkline, width, sparklineHeight) : '';
  const deltaTone = HOUSE_STYLE.colors.semantic.neutral;
  const deltaBg = '#F3F4F6';
  const deltaPrefix = model.deltaValue > 0 ? '+' : '';
  const targetCopy = model.targetValue > 0
    ? `<span style="font-size:${helperSize}px;color:${HOUSE_STYLE.colors.text.muted};font-weight:600;">Target ${formatCompact(model.targetValue)}</span>`
    : '';
  const targetGap = model.targetValue > 0
    ? model.currentValue - model.targetValue
    : 0;
  const targetGapCopy = model.targetValue > 0
    ? `<span style="font-size:${helperSize}px;color:${HOUSE_STYLE.colors.semantic.neutral};font-weight:700;">${targetGap >= 0 ? '+' : ''}${formatCompact(targetGap)} vs target</span>`
    : '';

  return `
    <div style="display:flex;flex-direction:column;justify-content:space-between;gap:${HOUSE_STYLE.spacing.md}px;width:${width}px;height:${height}px;">
      <div style="display:flex;align-items:flex-start;justify-content:space-between;gap:${HOUSE_STYLE.spacing.sm}px;flex-wrap:wrap;">
        <div>
          <div style="font-size:${valueSize}px;line-height:1;font-weight:800;letter-spacing:-0.03em;color:${HOUSE_STYLE.colors.text.strong};">${model.valueLabel}</div>
          <div style="margin-top:${HOUSE_STYLE.spacing.xs}px;display:flex;align-items:center;gap:${HOUSE_STYLE.spacing.xs}px;flex-wrap:wrap;">
            <span style="display:inline-flex;align-items:center;padding:4px 10px;border-radius:${HOUSE_STYLE.radius.chip}px;background:${model.stateAppearance.bg};color:${model.stateAppearance.fg};font-size:${helperSize}px;line-height:1.25;font-weight:800;">${model.stateLabel}</span>
            ${showDelta ? `<span style="display:inline-flex;align-items:center;padding:4px 10px;border-radius:${HOUSE_STYLE.radius.chip}px;background:${deltaBg};color:${deltaTone};font-size:${helperSize}px;line-height:1.25;font-weight:800;">${deltaPrefix}${formatCompact(model.deltaValue)} · ${formatPercent(model.deltaPercent, 1)}</span>` : ''}
          </div>
        </div>
        <div style="display:flex;flex-direction:column;align-items:flex-end;gap:${HOUSE_STYLE.spacing.xxs}px;">
          ${targetCopy}
          ${targetGapCopy}
          ${showDelta ? `<span style="font-size:${helperSize}px;line-height:1.35;color:${HOUSE_STYLE.colors.text.subtle};font-weight:700;letter-spacing:0.04em;text-transform:uppercase;">${model.comparisonLabel}</span>` : ''}
        </div>
      </div>
      ${model.noteText ? `<div style="font-size:${helperSize}px;line-height:1.35;font-weight:600;color:${HOUSE_STYLE.colors.text.muted};">${model.noteText}</div>` : ''}
      ${sparklineHtml ? `<div>${sparklineHtml}</div>` : ''}
    </div>
  `;
}

const model = buildCardModel();

module.exports = {
  cardVariant: model.cardVariant,
  render: Editor.wrapFn({
    args: [model],
    fn: function(options, currentModel) {
      function esc(value) {
        return String(value ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
      }
      function fmt(value) {
        const n = Number(value);
        if (!Number.isFinite(n)) return '—';
        const abs = Math.abs(n);
        if (abs >= 1000000) return `${(n / 1000000).toFixed(1).replace('.0', '')}M`;
        if (abs >= 1000) return `${(n / 1000).toFixed(1).replace('.0', '')}K`;
        return String(Math.round(n * 10) / 10).replace('.0', '');
      }
      function pct(value) {
        const n = Number(value);
        if (!Number.isFinite(n)) return 'n/a';
        return `${n > 0 ? '+' : ''}${n.toFixed(Math.abs(n) >= 10 ? 0 : 1).replace('.0', '')}%`;
      }
      function sparkline(points, width, height) {
        if (!points || points.length < 2) return '';
        const values = points.map((point) => Number(point.value) || 0);
        const min = Math.min.apply(null, values);
        const max = Math.max.apply(null, values);
        const span = Math.max(1, max - min);
        const pad = 5;
        const coordinates = points.map((point, index) => {
          const x = pad + (index / Math.max(1, points.length - 1)) * (width - pad * 2);
          const y = pad + (height - pad * 2) - ((Number(point.value) || 0) - min) / span * (height - pad * 2);
          return {x, y, id: point.id};
        });
        const line = coordinates.map((point) => `${point.x.toFixed(1)},${point.y.toFixed(1)}`).join(' ');
        const baseline = height - pad;
        const area = `${coordinates[0].x.toFixed(1)},${baseline} ${line} ${coordinates[coordinates.length - 1].x.toFixed(1)},${baseline}`;
        const dots = coordinates.map((point, index) => `<circle data-id="${esc(point.id)}" cx="${point.x.toFixed(1)}" cy="${point.y.toFixed(1)}" r="${index === coordinates.length - 1 ? 4 : 3}" fill="#2B75E2" stroke="#fff" stroke-width="1.5"></circle>`).join('');
        return `<svg width="100%" height="${height}" viewBox="0 0 ${width} ${height}" preserveAspectRatio="none" style="display:block;overflow:visible;"><polyline fill="rgba(43,117,226,0.12)" stroke="none" points="${area}"></polyline><polyline fill="none" stroke="#2B75E2" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" points="${line}"></polyline>${dots}</svg>`;
      }

      const rawWidth = Number(options && options.width) || 0;
      const rawHeight = Number(options && options.height) || 0;
      const width = rawWidth > 0 ? rawWidth : 420;
      const height = rawHeight > 0 ? rawHeight : 240;
      const dense = width < 380 || height < 190;
      const titleSize = dense ? 18 : 20;
      const valueSize = dense ? 32 : 42;
      const paddingX = dense ? 12 : 14;
      const paddingY = dense ? 10 : 12;
      const isEmpty = currentModel.status && currentModel.status !== 'ok';
      const deltaColor = '#5F6368';
      const deltaBg = '#F2F4F7';
      const body = isEmpty
        ? `<div style="flex:1;display:flex;align-items:center;justify-content:center;font-size:28px;line-height:34px;font-weight:800;color:#111827;">${currentModel.status === 'unavailable' ? 'SOURCE MISSING' : 'NO DATA'}</div>`
        : `<div style="display:flex;flex-direction:column;gap:${dense ? 8 : 10}px;min-height:0;flex:1;">
            <div style="display:flex;align-items:flex-start;justify-content:space-between;gap:12px;">
              <div style="font-size:${valueSize}px;line-height:${valueSize + 2}px;font-weight:800;color:#111827;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">${esc(currentModel.valueLabel || fmt(currentModel.currentValue))}</div>
              <div style="display:inline-flex;align-items:center;gap:6px;padding:${dense ? '5px 8px' : '6px 10px'};border-radius:999px;background:${deltaBg};color:${deltaColor};font-size:${dense ? 13 : 14}px;line-height:${dense ? 15 : 16}px;font-weight:800;white-space:nowrap;">${pct(currentModel.deltaPercent)}</div>
            </div>
            <div style="font-size:${dense ? 11 : 12}px;line-height:${dense ? 13 : 14}px;color:#98A2B3;text-transform:uppercase;letter-spacing:0.08em;font-weight:800;">${esc(currentModel.comparisonLabel || 'VS PREVIOUS PERIOD')}</div>
            ${currentModel.noteText ? `<div style="font-size:12px;line-height:16px;color:#667085;font-weight:600;">${esc(currentModel.noteText)}</div>` : ''}
            ${sparkline(currentModel.sparkline || [], Math.max(180, width - paddingX * 2), dense ? 46 : 60)}
          </div>`;

      return Editor.generateHtml(`
        <div style="box-sizing:border-box;width:100%;height:100%;padding:${paddingY}px ${paddingX}px;background:transparent;border:none;font-family:Inter,Arial,sans-serif;color:#111827;display:flex;flex-direction:column;gap:${dense ? 8 : 10}px;overflow:hidden;">
          <div style="display:flex;align-items:center;gap:8px;min-width:0;">
            <div style="font-size:${titleSize}px;line-height:${titleSize + 2}px;color:#5F6368;text-transform:uppercase;letter-spacing:0.08em;font-weight:800;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">${esc(currentModel.title)}</div>
            <div data-id="hint" style="display:inline-flex;align-items:center;justify-content:center;width:${dense ? 16 : 18}px;height:${dense ? 16 : 18}px;border-radius:999px;background:#F2F4F7;color:#667085;font-size:${dense ? 11 : 12}px;line-height:1;font-weight:800;cursor:help;flex:0 0 auto;">?</div>
          </div>
          ${currentModel.freshnessHtml || ''}
          ${body}
        </div>
      `);
    },
  }),
  tooltip: {
    renderer: Editor.wrapFn({
      args: [{
        title: model.title,
        helpBody: model.helpBody,
        helpSource: model.helpSource,
        items: model.tooltipItems || [],
      }],
      fn: function(event, payload) {
        function esc(value) {
          return String(value ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
        }
        const target = event && event.target;
        const closest = target && target.closest ? target.closest('[data-id]') : target;
        const id = closest && closest.getAttribute ? closest.getAttribute('data-id') : null;
        if (!id) return null;
        const match = id === 'hint'
          ? {title: payload.title, rows: [{label: 'Definition', value: payload.helpBody}, {label: 'Source', value: payload.helpSource}]}
          : payload.items.find((item) => item.id === id);
        if (!match) return null;
        const rows = (match.rows || []).map((row) => `<div style="display:flex;justify-content:space-between;gap:18px;margin-top:6px;"><span style="color:#667085;">${esc(row.label)}</span><span style="font-weight:800;color:#111827;">${esc(row.value)}</span></div>`).join('');
        return Editor.generateHtml(`<div style="min-width:220px;max-width:340px;padding:10px 12px;border-radius:10px;background:#fff;color:#111827;font-family:Inter,Arial,sans-serif;font-size:12px;line-height:16px;"><div style="font-weight:800;">${esc(match.title)}</div>${rows}</div>`);
      },
    }),
  },
};
