const qlConnectionId = Editor.getId('defaultConnection');

module.exports = {
  metricSummary: {
    qlConnectionId,
    data: {
      sql_query: `
        SELECT
          'Net retention' AS metric_title,
          'Retained revenue after expansions and contractions for the active date window.' AS help_text,
          'Canonical KPI family demo source' AS help_source,
          'Snapshot summary' AS source_label,
          'Static demo data' AS freshness_label,
          '2026-01-31 09:00 UTC' AS updated_at,
          42810 AS current_value,
          39120 AS previous_value,
          45000 AS target_value,
          'ok' AS state,
          'On track' AS state_label,
          'Vs previous month' AS comparison_label,
          'Target gap still visible but trend is healthy.' AS note_text
      `,
    },
  },
  sparklineSeries: {
    qlConnectionId,
    data: {
      sql_query: `
        SELECT '2026-01-01' AS event_date, 35210 AS metric_value
        UNION ALL SELECT '2026-01-05', 36180
        UNION ALL SELECT '2026-01-09', 37240
        UNION ALL SELECT '2026-01-13', 38910
        UNION ALL SELECT '2026-01-17', 40120
        UNION ALL SELECT '2026-01-21', 41780
        UNION ALL SELECT '2026-01-25', 42160
        UNION ALL SELECT '2026-01-31', 42810
      `,
    },
  },
};
