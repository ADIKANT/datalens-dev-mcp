// Data binding: use this only after table_node is proven insufficient.
module.exports = {
  rows: {
    qlConnectionId: Editor.getId('defaultConnection'),
    data: {
      sql_query: `SELECT 'Current' AS group_label, 'Completed' AS metric_label, 42 AS value`,
    },
  },
};
