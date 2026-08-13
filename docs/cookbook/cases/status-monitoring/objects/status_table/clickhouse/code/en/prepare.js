/**
 * Protected model preparation and renderer. A normal transfer does not require edits.
 * Route: editor_table. Technical parameter names and aliases are language-neutral.
 */
// The table stays a native table_node: pinning, cells, and headers are declared in head.
// Source/data contract: Sources returns rows with the selected variant's stable aliases.
// Params/config: table_variant selects one of four native table contracts.
// Prepare/model normalization: metadata/row events are converted into named objects.
// Render lifecycle: Prepare returns head/rows and table_node performs the rendering.
// Theme tokens: colors come from Gravity variables for light and dark themes.
// Interactions: pinning, links, hints, and pagination remain native table features.
// CUSTOMIZE — Optional customization: change values only inside this block.
const COOKBOOK_CUSTOMIZE = Object.freeze({
  palette: ['#2B75E2', '#F2994A', '#008A91', '#7A5AF8', '#D92D20'],
  numberFormat: 'decimal1',
  unit: '',
  emptyLabel: "No data",
});

const params = Editor.getParams ? (Editor.getParams() || {}) : {};
const rawVariant = Array.isArray(params.table_variant) ? params.table_variant[0] : params.table_variant;
const TABLE_VARIANT = ['standard', 'detail', 'status', 'grouped_summary'].includes(String(rawVariant))
  ? String(rawVariant)
  : 'standard';
const THEME = {
  text: 'var(--g-color-text-primary, inherit)',
  textSecondary: 'var(--g-color-text-secondary, inherit)',
  cellBg: 'var(--g-color-base-background, transparent)',
  headerBg: 'var(--g-color-base-neutral-light, transparent)',
  positiveBg: 'var(--g-color-base-positive-light, transparent)',
  warningBg: 'var(--g-color-base-warning-light, transparent)',
  dangerBg: 'var(--g-color-base-danger-light, transparent)',
};
const HEADER_CSS = {'background-color': THEME.headerBg, color: THEME.text, 'font-weight': 'normal', 'text-align': 'left'};
const BODY_CSS = {color: THEME.text, 'background-color': THEME.cellBg};
const TABLE_COPY = Object.freeze({
  noData: 'No data', checkSources: 'Check sources.js', identifier: 'Identifier', object: 'Object',
  status: 'Status', owner: 'Owner', updated: 'Updated', amount: 'Amount', details: 'Details',
  item: 'Item', category: 'Category', completion: 'Completion', completed: 'Completed', total: 'Total', progress: 'Progress', open: 'Open',
  ready: 'Ready', warning: 'Needs attention', review: 'In review', error: 'Error', failed: 'Failed', unknown: 'Unknown',
});

function tableObjects(sourceName) {
  const loaded = Editor.getLoadedData() || {};
  const source = loaded[sourceName] || [];
  const metadata = Array.isArray(source) ? source.find((item) => item && item.event === 'metadata') : null;
  const names = metadata?.data?.names || [];
  return (Array.isArray(source) ? source : [])
    .filter((item) => item && item.event === 'row')
    .map((item) => Object.fromEntries(names.map((name, index) => [name, item.data[index]])));
}

function safeHttps(value) {
  const text = String(value || '').trim();
  return /^https:\/\/[^\s]+$/i.test(text) ? text : '';
}

function formattedNumber(value) {
  if (value === null || value === undefined || value === '' || !Number.isFinite(Number(value))) return '—';
  return new Intl.NumberFormat('en-US', {maximumFractionDigits: 2}).format(Number(value));
}

function statusCss(value) {
  const key = String(value || '').toLowerCase();
  const background = key === 'ready' || key === 'ok'
    ? THEME.positiveBg
    : key === 'warning' || key === 'review'
      ? THEME.warningBg
      : key === 'error' || key === 'failed'
        ? THEME.dangerBg
        : THEME.cellBg;
  return {...BODY_CSS, 'background-color': background, 'font-weight': '600'};
}

function statusLabel(value) {
  const key = String(value || '').toLowerCase();
  return TABLE_COPY[key] || TABLE_COPY.unknown;
}

const objects = tableObjects('rows');
let head = [];
let rows = [];

if (TABLE_VARIANT === 'detail') {
  head = [
    {id: 'entity_id', name: TABLE_COPY.identifier, type: 'text', pinned: true, width: 126, hint: 'Stable row key', css: HEADER_CSS},
    {id: 'entity_name', name: TABLE_COPY.object, type: 'text', pinned: true, width: 220, hint: 'Primary display name', css: HEADER_CSS},
    {id: 'status', name: TABLE_COPY.status, type: 'status', width: 120, css: HEADER_CSS},
    {id: 'owner', name: TABLE_COPY.owner, type: 'text', width: 160, css: HEADER_CSS},
    {id: 'updated_at', name: TABLE_COPY.updated, type: 'datetime', width: 170, hint: 'ISO-8601 source value', css: HEADER_CSS},
    {id: 'amount', name: TABLE_COPY.amount, type: 'number', width: 140, css: HEADER_CSS},
  ];
  rows = objects.filter((item) => item.entity_id).map((item, index) => ({
    id: String(item.entity_id || `row_${index + 1}`),
    cells: [
      {value: item.entity_id, css: BODY_CSS},
      {value: item.entity_name || item.entity_id, css: BODY_CSS},
      {value: item.status || '', formattedValue: statusLabel(item.status), css: statusCss(item.status)},
      {value: item.owner || '—', css: BODY_CSS},
      {value: item.updated_at || TABLE_COPY.noData, css: BODY_CSS},
      {value: item.amount, formattedValue: formattedNumber(item.amount), css: BODY_CSS},
    ],
  }));
} else if (TABLE_VARIANT === 'status') {
  head = [
    {id: 'entity_id', name: TABLE_COPY.identifier, type: 'text', pinned: true, width: 126, css: HEADER_CSS},
    {id: 'item', name: TABLE_COPY.item, type: 'text', width: 260, css: HEADER_CSS},
    {id: 'status', name: TABLE_COPY.status, type: 'status', width: 140, css: HEADER_CSS},
    {id: 'updated_at', name: TABLE_COPY.updated, type: 'datetime', width: 180, css: HEADER_CSS},
    {id: 'details_url', name: TABLE_COPY.details, type: 'link', width: 100, css: HEADER_CSS},
  ];
  rows = objects.filter((item) => item.entity_id).map((item, index) => {
    const href = safeHttps(item.details_url);
    return {
      id: String(item.entity_id || `row_${index + 1}`),
      cells: [
        {value: item.entity_id, css: BODY_CSS},
        {value: item.item || item.entity_id, css: BODY_CSS},
        {value: item.status || '', formattedValue: statusLabel(item.status), css: statusCss(item.status)},
        {value: item.updated_at || TABLE_COPY.noData, css: BODY_CSS},
        {value: href, href, formattedValue: href ? TABLE_COPY.open : '—', css: BODY_CSS},
      ],
    };
  });
} else if (TABLE_VARIANT === 'grouped_summary') {
  head = [
    {id: 'category', name: TABLE_COPY.category, type: 'text', pinned: true, width: 220, css: HEADER_CSS},
    {id: 'completion', name: TABLE_COPY.completion, sub: [
      {id: 'completed', name: TABLE_COPY.completed, type: 'bar', min: 0, max: Math.max(1, ...objects.map((item) => Number(item.total) || 0)), barColor: '#2B75E2', showLabel: true, css: HEADER_CSS},
      {id: 'total', name: TABLE_COPY.total, type: 'number', css: HEADER_CSS},
      {id: 'progress', name: TABLE_COPY.progress, type: 'progress', min: 0, max: 100, barColor: '#008A91', showLabel: true, css: HEADER_CSS},
    ]},
  ];
  rows = objects.filter((item) => item.category).map((item, index) => {
    const completed = Math.max(0, Number(item.completed) || 0);
    const total = Math.max(0, Number(item.total) || 0);
    const progress = total > 0 ? Math.min(100, completed / total * 100) : 0;
    return {id: `row_${index + 1}`, cells: [
      {value: item.category, css: BODY_CSS},
      {value: completed, formattedValue: formattedNumber(completed), css: BODY_CSS},
      {value: total, formattedValue: formattedNumber(total), css: BODY_CSS},
      {value: progress, formattedValue: `${Math.round(progress)}%`, css: BODY_CSS},
    ]};
  });
} else {
  const names = ['status', 'item', 'value'];
  const maximum = Math.max(1, ...objects.map((item) => Number(item.value) || 0));
  head = [
    {id: 'status', name: TABLE_COPY.status, type: 'status', css: HEADER_CSS},
    {id: 'item', name: TABLE_COPY.item, type: 'text', css: HEADER_CSS},
    {id: 'value', name: 'Value', type: 'bar', min: 0, max: maximum, barColor: '#2B75E2', barHeight: '70%', showLabel: true, css: HEADER_CSS},
  ];
  rows = objects.map((item, index) => ({id: `row_${index + 1}`, cells: names.map((name) => ({value: item[name] ?? '', formattedValue: name === 'status' ? statusLabel(item[name]) : undefined, css: name === 'status' ? statusCss(item[name]) : BODY_CSS}))}));
}

if (!rows.length) {
  const leafCount = head.reduce((count, item) => count + (Array.isArray(item.sub) ? item.sub.length : 1), 0);
  rows = [{id: 'empty', cells: Array.from({length: leafCount}, (_unused, index) => ({value: index === 0 ? TABLE_COPY.noData : index === 1 ? TABLE_COPY.checkSources : '', css: BODY_CSS}))}];
}

module.exports = {head, rows, tableVariant: TABLE_VARIANT};
