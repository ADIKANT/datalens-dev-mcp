// Data binding: output rows with stable table columns.
module.exports = {
  rows: {
    qlConnectionId: Editor.getId('defaultConnection'),
    data: {
      sql_query: `SELECT 'Ready' AS status, 'Example row' AS item, 1 AS value`,
    },
  },
};
