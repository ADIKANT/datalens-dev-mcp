// Fixture binding: bullet variants consume an explicit target; production sources are caller-bound.
module.exports = {
  rows: {
    qlConnectionId: Editor.getId('defaultConnection'),
    data: {
      sql_query: `
        SELECT 'In Progress' AS label, 'All' AS group, 42 AS value, 40 AS target
        UNION ALL SELECT 'Done', 'All', 38, 36
        UNION ALL SELECT 'To Do', 'All', 21, 24
      `,
    },
  },
};
