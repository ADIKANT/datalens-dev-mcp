module.exports = {
  environmentOptions: {
    qlConnectionId: Editor.getId('exampleConnection'),
    data: {
      sql_query: `
        SELECT 'dev' AS environment
        UNION ALL
        SELECT 'stage' AS environment
        UNION ALL
        SELECT 'prod' AS environment
      `
    },
    ui: true
  }
};
