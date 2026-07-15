module.exports = {
  rows: {
    qlConnectionId: Editor.getId('exampleConnection'),
    data: {
      sql_query: `
        SELECT
          'Ready' AS status,
          'Example row' AS item,
          1 AS value
      `
    }
  }
};
