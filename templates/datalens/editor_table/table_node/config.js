// @cookbook-locale ru Config управляет нативной пагинацией, плотностью и горизонтальной прокруткой.
// @cookbook-locale en Config controls native pagination, density, and horizontal scrolling.
const params = Editor.getParams ? (Editor.getParams() || {}) : {};
const rawPageSize = Array.isArray(params.page_size) ? params.page_size[0] : params.page_size;
const requestedPageSize = Number(rawPageSize == null || rawPageSize === '' ? 100 : rawPageSize);
const pageSize = Number.isInteger(requestedPageSize) && requestedPageSize >= 1 && requestedPageSize <= 200
  ? requestedPageSize
  : 100;
const rawVariant = Array.isArray(params.table_variant) ? params.table_variant[0] : params.table_variant;
const tableVariant = ['standard', 'detail', 'status', 'grouped_summary'].includes(String(rawVariant))
  ? String(rawVariant)
  : 'standard';
module.exports = {
  title: tableVariant === 'detail' ? 'Detail table' : tableVariant === 'status' ? 'Status table' : tableVariant === 'grouped_summary' ? 'Grouped summary' : 'Standard table',
  size: tableVariant === 'detail' ? 's' : 'm',
  paginator: {enabled: true, limit: pageSize},
  horizontalScroll: tableVariant === 'detail' || tableVariant === 'status',
  pinnedColumnCount: tableVariant === 'detail' ? 2 : 1,
  emptyState: {title: 'No data', description: 'Check sources.js and active Params'},
};
