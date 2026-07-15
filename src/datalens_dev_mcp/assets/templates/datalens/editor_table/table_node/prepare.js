/*
 * Editor Table template contract:
 * - Source/data contract: sources.js returns metadata and row events with stable column order.
 * - Params/config: params.json/config.js own paginator, density, and table options.
 * - Prepare/model normalization: prepare.js converts loaded events into head/rows only.
 * - Render lifecycle: table_node renders head/rows natively, no ad hoc HTML render.
 * - Layout/scales: table sizing is route-native; selector rows use dashboard relation rules.
 * - Labels/tooltips: column names come from metadata, not duplicated dashboard titles.
 * - Theme tokens: CSS uses DataLens/Gravity variables for light and dark themes.
 * - Interactions: selector bindings live in dashboard relations, not hidden in table cells.
 */
const THEME = {
  text: 'var(--g-color-text-primary, inherit)',
  textSecondary: 'var(--g-color-text-secondary, inherit)',
  cellBg: 'var(--g-color-base-background, transparent)',
  headerBg: 'var(--g-color-base-neutral-light, transparent)',
};
const HEADER_CSS = {
  'background-color': THEME.headerBg,
  color: THEME.text,
  'font-weight': 'normal',
  'text-align': 'left',
};
const BODY_CSS = {
  color: THEME.text,
  'background-color': THEME.cellBg,
};
const loaded = Editor.getLoadedData() || {};
const source = loaded.rows || [];
const metadata = Array.isArray(source) ? source.find((item) => item && item.event === 'metadata') : null;
const names = metadata?.data?.names || ['status', 'item', 'value'];
const rawRows = Array.isArray(source) ? source.filter((item) => item && item.event === 'row') : [];
const rows = rawRows.length
  ? rawRows.map((item, index) => ({id: `row_${index + 1}`, cells: item.data.map((value) => ({value, css: BODY_CSS}))}))
  : [{id: 'row_1', cells: [{value: 'No data', css: BODY_CSS}, {value: 'Adjust sources.js', css: BODY_CSS}, {value: 0, css: BODY_CSS}]}];
const values = rows.map((row) => Number(((row.cells || [])[names.indexOf('value')] || {}).value || 0));
const maxValue = Math.max(1, ...values);
const head = names.map((name) => name === 'value'
  ? ({id: name, name, type: 'bar', min: 0, max: maxValue, barColor: '#2f80ed', barHeight: '70%', showLabel: true, css: HEADER_CSS})
  : ({id: name, name, type: 'text', css: HEADER_CSS}));

module.exports = {head, rows};
