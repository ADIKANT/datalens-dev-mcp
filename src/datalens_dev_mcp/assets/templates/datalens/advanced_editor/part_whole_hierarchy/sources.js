// Data binding: output label/value rows; hierarchy can add parent_label.
module.exports = {
  rows: {
    qlConnectionId: Editor.getId('defaultConnection'),
    data: {
      sql_query: `
        SELECT 'High' AS label, 16 AS value
        UNION ALL SELECT 'Medium', 42
        UNION ALL SELECT 'Low', 28
      `,
    },
  },
};
