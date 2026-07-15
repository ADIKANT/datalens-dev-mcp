const qlConnectionId = Editor.getId('defaultConnection');

module.exports = {
  tableRows: {
    qlConnectionId,
    data: {
      sql_query: `
        SELECT 'Core API' AS group_name, 'service-a' AS item_name, '1.2.3' AS current_version, '1.2.4' AS target_version, 'Ready' AS release_state
        UNION ALL SELECT 'Core API', 'service-b', '2.0.1', '2.1.0', 'Review'
        UNION ALL SELECT 'Data jobs', 'etl-main', '5.4.0', '5.4.2', 'Blocked'
      `,
    },
  },
};
