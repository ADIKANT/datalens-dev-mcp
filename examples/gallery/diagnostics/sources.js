module.exports = {
  actionRows: {
    qlConnectionId: Editor.getId('defaultConnection'),
    data: {
      sql_query: `
        SELECT 'Focus area' AS card_label, 'Funnel leakage' AS primary_text, '12% conversion' AS secondary_text, 'warning' AS state_tone
        UNION ALL SELECT 'Lead source', 'Organic', '42% share', 'ok'
        UNION ALL SELECT 'Latest change', '+8%', 'week over week', 'neutral'
      `,
    },
  },
};
