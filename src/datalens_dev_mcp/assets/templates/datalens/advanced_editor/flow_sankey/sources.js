// Data binding: output source, target, and value. Do not use this for ordinary category counts.
module.exports = {
  rows: {
    qlConnectionId: Editor.getId('defaultConnection'),
    data: {
      sql_query: `
        SELECT 'To Do' AS source, 'In Progress' AS target, 42 AS value
        UNION ALL SELECT 'In Progress', 'Done', 34
      `,
    },
  },
};
