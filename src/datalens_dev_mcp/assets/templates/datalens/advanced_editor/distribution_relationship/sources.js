// Fixture binding: box-plot statistics are explicit; production sources are caller-bound.
module.exports = {
  rows: {
    qlConnectionId: Editor.getId('defaultConnection'),
    data: {
      sql_query: `
        SELECT '0-7' AS label, 20 AS value, 3 AS x, 12 AS y, 5 AS size,
               1 AS min, 4 AS q1, 7 AS median, 12 AS q3, 18 AS max
        UNION ALL SELECT '8-14', 14, 11, 16, 8, 3, 6, 9, 14, 20
      `,
    },
  },
};
