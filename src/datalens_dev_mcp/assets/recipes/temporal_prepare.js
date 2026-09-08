/* Normalize supported calendar grids in Prepare; never interpolate or alter KPI summaries. */
module.exports = function prepareTime(data, date, recipe) {
  if (!data || typeof data !== 'object') return data;
  const kpi = recipe === 'kpi_sparkline';
  const labels = kpi ? (data.points || []).map(p => p.date) : (data.categories || []);
  const mode = date.mode || 'auto';
  if (!['auto', 'calendar', 'temporal', 'ordinal'].includes(mode)) throw new Error('date.mode must be auto, calendar, temporal or ordinal');
  const granularity = date.granularity || (['day', 'week', 'month'].includes(data.grain) ? data.grain : null);
  if (granularity && !['day', 'week', 'month'].includes(granularity)) throw new Error('date.granularity must be day, week or month');
  if (mode === 'ordinal' || !labels.length) return {...data, time_mode: 'ordinal'};
  const iso = value => typeof value === 'string' && /^\d{4}-\d{2}-\d{2}(?:T.*)?$/.test(value);
  const timestamps = labels.map(value => iso(value) ? Date.parse(value) : NaN);
  if (timestamps.some(value => !Number.isFinite(value))) {
    if (mode !== 'auto' || date.granularity) throw new Error('calendar dates must be ISO dates or timestamps');
    return {...data, time_mode: 'ordinal'};
  }
  if (new Set(timestamps).size !== timestamps.length) throw new Error('calendar series requires one observation per timestamp');
  const indices = timestamps.map((_, i) => i).sort((a, b) => timestamps[a] - timestamps[b]);
  let grid = indices.map(i => timestamps[i]);
  const byTime = new Map(timestamps.map((time, i) => [time, i]));
  if (granularity && mode !== 'temporal') {
    const start = grid[0], end = grid[grid.length - 1];
    const next = timestamp => {
      if (granularity === 'day') return timestamp + 86400000;
      if (granularity === 'week') return timestamp + 604800000;
      const d = new Date(timestamp);
      if (d.getUTCDate() !== 1) throw new Error('monthly grid requires month-start dates');
      d.setUTCMonth(d.getUTCMonth() + 1);
      return d.getTime();
    };
    grid = [];
    for (let time = start; time <= end; time = next(time)) {
      if (grid.length >= 10000) throw new Error('calendar grid exceeds 10000 periods');
      grid.push(time);
    }
    const expected = new Set(grid);
    if (timestamps.some(time => !expected.has(time))) throw new Error('observations do not align with date.granularity');
  }
  const aligned = values => grid.map(time => byTime.has(time) ? values[byTime.get(time)] : null);
  const outputMode = granularity && mode !== 'temporal' ? 'ordinal' : 'temporal';
  if (kpi) return {...data, time_mode: outputMode, points: grid.map(time => {
    const i = byTime.get(time);
    return i === undefined ? {date: new Date(time).toISOString().slice(0, 10), value: null, timestamp: time}
      : {...data.points[i], timestamp: time};
  })};
  const result = {...data, time_mode: outputMode, timestamps: grid,
    categories: grid.map(time => byTime.has(time) ? labels[byTime.get(time)] : new Date(time).toISOString().slice(0, 10)),
    series: data.series.map(item => ({...item, values: aligned(item.values),
      ...(item.comparisonValues ? {comparisonValues: aligned(item.comparisonValues)} : {})}))};
  for (const key of ['comparisonCategories', 'currentRanges', 'comparisonRanges']) {
    if (Array.isArray(data[key])) result[key] = aligned(data[key]);
  }
  return result;
};
