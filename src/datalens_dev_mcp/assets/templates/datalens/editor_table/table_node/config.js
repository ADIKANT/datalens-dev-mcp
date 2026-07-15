// Table configuration: keep this route as table_node, not an Advanced HTML chart.
const params = Editor.getParams ? (Editor.getParams() || {}) : {};
const rawPageSize = Array.isArray(params.page_size) ? params.page_size[0] : params.page_size;
const requestedPageSize = Number(rawPageSize == null || rawPageSize === '' ? 100 : rawPageSize);
const pageSize = Number.isInteger(requestedPageSize) && requestedPageSize >= 1 && requestedPageSize <= 200
  ? requestedPageSize
  : 100;
module.exports = {
  title: 'Standard table',
  size: 'm',
  paginator: {enabled: true, limit: pageSize},
};
