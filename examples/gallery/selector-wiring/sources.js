const qlConnectionId = Editor.getId('defaultConnection');

module.exports = {
  regionOptions: {
    qlConnectionId,
    ui: true,
    data: {
      sql_query: `
        SELECT DISTINCT region
        FROM analytics.locations
        ORDER BY region
      `,
    },
  },
  countryOptions: {
    qlConnectionId,
    ui: true,
    data: {
      sql_query: `
        SELECT DISTINCT region, country
        FROM analytics.locations
        ORDER BY region, country
      `,
    },
  },
};
