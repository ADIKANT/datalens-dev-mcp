/* Canonical comparison matrix renderer with a fixed semantic legend. */
module.exports = function renderMatrix(data, config) {
  const rows = data && Array.isArray(data.rows) ? data.rows : [];
  return {
    type: 'comparison-matrix',
    state: data && data.state ? data.state : (rows.length ? 'ready' : 'no_data'),
    rows,
    legend: config.legend,
    columns: config.table.columns,
    tooltip: config.tooltip,
    geometry: config.geometry
  };
};
