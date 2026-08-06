/*
 * Deterministic adapter for the immutable registered standard dashboard renderer.
 * Business SQL must expose the registered family columns through the `rows`
 * source. This adapter only converts those rows into the renderer's chartData
 * contract; the registered renderer below is injected byte-for-byte.
 */
const DASHBOARD_RENDER_SPEC = __DATALENS_DASHBOARD_RENDER_SPEC__;

function profileTextForMode(value, mode) {
  return DASHBOARD_RENDER_SPEC.title_mode === mode ? String(value || '') : '';
}

function profileEmbeddedTitle() {
  return profileTextForMode(DASHBOARD_RENDER_SPEC.title, 'embedded_title');
}

function profileEmbeddedHint() {
  return profileTextForMode(DASHBOARD_RENDER_SPEC.hint, 'embedded_title');
}

function profileContentLabel() {
  return profileTextForMode(DASHBOARD_RENDER_SPEC.title, 'content_label');
}

function profileContentHint() {
  return profileTextForMode(DASHBOARD_RENDER_SPEC.hint, 'content_label');
}

function profileLoadedRows(sourceName) {
  const sourceData = Editor.getLoadedData()[sourceName] || [];
  const metadata = sourceData.find((item) => item.event === 'metadata');
  const names = metadata?.data?.names || [];
  return sourceData
    .filter((item) => item.event === 'row')
    .map((item) => {
      const row = {};
      item.data.forEach((value, index) => {
        row[names[index]] = value;
      });
      return row;
    });
}

function profileFinite(value) {
  if (value === null || value === undefined || value === '') return null;
  const numeric = Number(value);
  return Number.isFinite(numeric) ? numeric : null;
}

function profileNumberArray(value) {
  if (Array.isArray(value)) return value.map(profileFinite);
  if (typeof value !== 'string' || !value.trim()) return [];
  try {
    const parsed = JSON.parse(value);
    if (Array.isArray(parsed)) return parsed.map(profileFinite);
  } catch (_error) {
    return value.split(',').map((item) => profileFinite(item.trim()));
  }
  return [];
}

function profileUnique(values) {
  const seen = new Set();
  const result = [];
  values.forEach((value) => {
    const normalized = String(value ?? '');
    if (!normalized || seen.has(normalized)) return;
    seen.add(normalized);
    result.push(normalized);
  });
  return result;
}

function profileDelta(current, previous) {
  const currentValue = profileFinite(current);
  const previousValue = profileFinite(previous);
  if (currentValue === null || previousValue === null) return {percent: null, tone: 'neutral'};
  const difference = currentValue - previousValue;
  const percent = previousValue === 0 ? null : difference * 100 / Math.abs(previousValue);
  return {
    percent,
    tone: difference > 0 ? 'positive' : difference < 0 ? 'negative' : 'neutral'
  };
}

function profileTimeChart(rows, adapter) {
  const categories = profileUnique(rows.map((row) => row.bucket));
  const metrics = profileUnique(rows.map((row) => row.metric || DASHBOARD_RENDER_SPEC.title || 'Value'));
  const colors = ['#2B75E2', '#F2994A', '#008A91', '#7A5AF8', '#D92D20'];
  const explicitComparison = rows.some((row) => String(row.series_role || '').toLowerCase() === 'comparison');
  function values(metric, comparison) {
    return categories.map((bucket) => {
      const row = rows.find((candidate) => {
        const candidateMetric = String(candidate.metric || DASHBOARD_RENDER_SPEC.title || 'Value');
        const role = String(candidate.series_role || 'current').toLowerCase();
        return String(candidate.bucket || '') === bucket
          && candidateMetric === metric
          && (comparison ? role === 'comparison' : role !== 'comparison');
      });
      return row ? profileFinite(row.value) : null;
    });
  }
  const series = metrics.map((metric, index) => {
    let type = adapter === 'combo_bar' ? 'bar' : 'line';
    if (adapter === 'combo_mixed') {
      const declared = rows.find((row) => String(row.metric || DASHBOARD_RENDER_SPEC.title || 'Value') === metric)?.series_type;
      type = declared === 'line' || declared === 'bar' ? declared : index === 0 ? 'bar' : 'line';
    }
    const currentValues = values(metric, false);
    return {
      name: metric,
      comparisonLegendName: explicitComparison ? `${metric} · comparison` : '',
      type,
      color: colors[index % colors.length],
      values: currentValues,
      comparisonValues: explicitComparison ? values(metric, true) : [],
      format: 'decimal1',
      unit: '',
      summaryValue: currentValues.filter((value) => value !== null).slice(-1)[0] ?? null
    };
  }).filter((item) => (
    item.values.some((value) => value !== null)
    || item.comparisonValues.some((value) => value !== null)
  ));
  const monthly = categories.length > 0 && categories.every((value) => /^\d{4}-\d{2}$/.test(value));
  return {
    kind: 'combo',
    title: profileEmbeddedTitle(),
    subtitle: profileEmbeddedHint(),
    hasCurrentData: series.some((item) => item.values.some((value) => value !== null)),
    grain: monthly ? 'month' : 'day',
    categories,
    comparisonCategories: categories,
    currentRanges: categories,
    comparisonRanges: categories,
    comparisonLabel: 'Comparison',
    primaryFormat: 'decimal1',
    series
  };
}

function profileHorizontalChart(rows, grouped) {
  const labels = profileUnique(rows.map((row) => row.label));
  const groups = grouped
    ? profileUnique(rows.map((row) => row.group || 'All'))
    : ['Value'];
  const colors = ['#2B75E2', '#98A2B3', '#F2994A', '#008A91', '#7A5AF8'];
  return {
    kind: 'horizontal',
    title: profileEmbeddedTitle(),
    subtitle: profileEmbeddedHint(),
    hasCurrentData: rows.some((row) => profileFinite(row.value) !== null),
    valueFormat: 'decimal1',
    series: groups.map((group, index) => ({name: group, color: colors[index % colors.length]})),
    rows: labels.map((label) => ({
      label,
      values: groups.map((group) => {
        const row = rows.find((candidate) => String(candidate.label || '') === label
          && (!grouped || String(candidate.group || 'All') === group));
        return row ? profileFinite(row.value) : null;
      })
    }))
  };
}

function profileMetricTile(rows) {
  const row = rows[0] || {};
  const current = profileFinite(row.current_value ?? row.value);
  const previous = profileFinite(row.comparator_value);
  return {
    kind: 'metric-tile',
    title: '',
    hasCurrentData: current !== null,
    grain: '',
    categories: [],
    comparisonCategories: [],
    currentRanges: [],
    comparisonRanges: [],
    previousLabel: 'Comparison',
    cards: [{
      label: profileContentLabel(),
      value: current,
      previous,
      delta: profileDelta(current, previous),
      format: 'decimal1',
      unit: '',
      accent: '#2B75E2',
      status: '',
      note: profileContentHint(),
      sparkline: profileNumberArray(row.sparkline),
      comparisonSparkline: profileNumberArray(row.comparison_sparkline)
    }]
  };
}

const profileRows = profileLoadedRows('rows');
let chartData;
if (DASHBOARD_RENDER_SPEC.adapter === 'metric_tile') {
  chartData = profileMetricTile(profileRows);
} else if (DASHBOARD_RENDER_SPEC.adapter === 'combo_line') {
  chartData = profileTimeChart(profileRows, 'combo_line');
} else if (DASHBOARD_RENDER_SPEC.adapter === 'combo_bar') {
  chartData = profileTimeChart(profileRows, 'combo_bar');
} else if (DASHBOARD_RENDER_SPEC.adapter === 'combo_mixed') {
  chartData = profileTimeChart(profileRows, 'combo_mixed');
} else if (DASHBOARD_RENDER_SPEC.adapter === 'horizontal') {
  chartData = profileHorizontalChart(profileRows, false);
} else if (DASHBOARD_RENDER_SPEC.adapter === 'horizontal_grouped') {
  chartData = profileHorizontalChart(profileRows, true);
} else {
  throw new Error(`Unsupported registered standard dashboard adapter: ${DASHBOARD_RENDER_SPEC.adapter}`);
}

/* __DATALENS_STANDARD_DASHBOARD_RUNTIME__ */

module.exports = createChart(chartData);
