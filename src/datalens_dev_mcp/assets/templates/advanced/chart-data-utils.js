const {HOUSE_STYLE} = require('./style-tokens');

function toNumber(value, fallback = 0) {
  const number = Number(value);
  return Number.isFinite(number) ? number : fallback;
}

function toStringValue(value, fallback = '') {
  return value === undefined || value === null || value === '' ? fallback : String(value);
}

function formatInteger(value) {
  return String(Math.round(toNumber(value))).replace(/\B(?=(\d{3})+(?!\d))/g, ',');
}

function formatCompact(value) {
  const number = toNumber(value);
  const abs = Math.abs(number);
  if (abs >= 1000000) return `${(number / 1000000).toFixed(abs >= 10000000 ? 0 : 1).replace(/\.0$/, '')}M`;
  if (abs >= 1000) return `${(number / 1000).toFixed(abs >= 10000 ? 0 : 1).replace(/\.0$/, '')}K`;
  return formatInteger(number);
}

function formatPercent(value, digits = 0) {
  return `${toNumber(value).toFixed(digits)}%`;
}

function safeId(value) {
  return String(value == null ? 'item' : value).replace(/[^\w-]+/g, '_').slice(0, 80) || 'item';
}

function normalizeRows(loaded) {
  if (!loaded) return [];
  if (Array.isArray(loaded)) {
    const meta = loaded.find((item) => item && item.event === 'metadata');
    const names = meta?.data?.names || [];
    const eventRows = loaded.filter((item) => item && item.event === 'row' && Array.isArray(item.data));
    if (names.length && eventRows.length) {
      return eventRows.map((rowItem) => Object.fromEntries(rowItem.data.map((value, index) => [names[index] || `column_${index + 1}`, value])));
    }
    return loaded;
  }
  const fields = (loaded.fields || loaded.columns || []).map((field, index) => field.title || field.name || field.guid || `column_${index + 1}`);
  const rows = loaded.rows || loaded.data || loaded.values || loaded.result?.data?.Data || [];
  if (fields.length && Array.isArray(rows)) {
    return rows.map((row) => Array.isArray(row) ? Object.fromEntries(row.map((value, index) => [fields[index] || `column_${index + 1}`, value])) : row);
  }
  return [];
}

function getSourceRows(sourceName) {
  try {
    const direct = Editor.getLoadedData(sourceName);
    const directRows = normalizeRows(direct);
    if (directRows.length) return directRows;
  } catch (error) {
    // DataLens may not support direct named-source access in older runtimes.
  }
  const loaded = Editor.getLoadedData() || {};
  return normalizeRows(loaded[sourceName] || loaded);
}

function getParamScalar(name, fallback = '') {
  const params = Editor.getParams ? Editor.getParams() : {};
  const value = params && params[name];
  return Array.isArray(value) ? toStringValue(value[0], fallback) : toStringValue(value, fallback);
}

function sumBy(rows, key) {
  return rows.reduce((sum, row) => sum + toNumber(row[key]), 0);
}

function sortDesc(rows, key) {
  return [...rows].sort((left, right) => toNumber(right[key]) - toNumber(left[key]));
}

function groupBy(rows, getKey) {
  const grouped = new Map();
  for (const row of rows) {
    const key = getKey(row);
    if (!grouped.has(key)) grouped.set(key, []);
    grouped.get(key).push(row);
  }
  return grouped;
}

function clamp(value, min, max) {
  return Math.min(max, Math.max(min, toNumber(value)));
}

function withPalette(rows) {
  const colors = Object.values(HOUSE_STYLE.colors.data);
  return rows.map((row, index) => ({...row, color: row.color || colors[index % colors.length] || HOUSE_STYLE.colors.data.primary}));
}

function bucketTailToOther(rows, options = {}) {
  const maxItems = options.maxItems || 8;
  const valueKey = options.valueKey || 'value';
  if (rows.length <= maxItems) return rows;
  const head = rows.slice(0, maxItems - 1);
  const tailValue = sumBy(rows.slice(maxItems - 1), valueKey);
  return [...head, {label: 'Other', [valueKey]: tailValue, color: HOUSE_STYLE.colors.data.other}];
}

module.exports = {
  bucketTailToOther,
  clamp,
  formatCompact,
  formatInteger,
  formatPercent,
  getParamScalar,
  getSourceRows,
  groupBy,
  safeId,
  sortDesc,
  sumBy,
  toNumber,
  toStringValue,
  withPalette,
};
