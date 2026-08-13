// @cookbook-locale ru В production замените fixture своим dataset binding и сохраните порядок aliases.
// @cookbook-locale en In production replace the fixture with your dataset binding and preserve alias order.
// Fixture only: production generation replaces this SQL with a caller-owned dataset binding.
// Keep the table column order stable in the production Sources tab.
module.exports = {
  rows: {
    qlConnectionId: Editor.getId('defaultConnection'),
    data: {
      sql_query: `SELECT 'Ready' AS status, 'Example row' AS item, 1 AS value`,
    },
  },
};
