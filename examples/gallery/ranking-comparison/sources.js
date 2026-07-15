const qlConnectionId = Editor.getId('defaultConnection');

module.exports = {
  horizontalBarRows: {
    qlConnectionId,
    data: {
      sql_query: `
        SELECT 'Organic' AS category_label, 128 AS metric_value
        UNION ALL SELECT 'Paid', 101
        UNION ALL SELECT 'CRM', 74
        UNION ALL SELECT 'Referral', 53
        UNION ALL SELECT 'Affiliates', 34
        UNION ALL SELECT 'Retail', 21
      `,
    },
  },
  groupedBarRows: {
    qlConnectionId,
    data: {
      sql_query: `
        SELECT 'North' AS category_label, 'Current' AS series_label, 82 AS metric_value
        UNION ALL SELECT 'North', 'Previous', 67
        UNION ALL SELECT 'South', 'Current', 71
        UNION ALL SELECT 'South', 'Previous', 64
        UNION ALL SELECT 'East', 'Current', 63
        UNION ALL SELECT 'East', 'Previous', 59
        UNION ALL SELECT 'West', 'Current', 58
        UNION ALL SELECT 'West', 'Previous', 55
      `,
    },
  },
  normalizedStackRows: {
    qlConnectionId,
    data: {
      sql_query: `
        SELECT 'W1' AS bucket_label, 'Organic' AS segment_label, 48 AS metric_value
        UNION ALL SELECT 'W1', 'Paid', 30
        UNION ALL SELECT 'W1', 'CRM', 22
        UNION ALL SELECT 'W2', 'Organic', 44
        UNION ALL SELECT 'W2', 'Paid', 34
        UNION ALL SELECT 'W2', 'CRM', 22
        UNION ALL SELECT 'W3', 'Organic', 39
        UNION ALL SELECT 'W3', 'Paid', 38
        UNION ALL SELECT 'W3', 'CRM', 23
        UNION ALL SELECT 'W4', 'Organic', 36
        UNION ALL SELECT 'W4', 'Paid', 41
        UNION ALL SELECT 'W4', 'CRM', 23
      `,
    },
  },
  heatmapRows: {
    qlConnectionId,
    data: {
      sql_query: `
        SELECT 'North' AS row_label, 'Jan' AS col_label, 63 AS metric_value
        UNION ALL SELECT 'North', 'Feb', 71
        UNION ALL SELECT 'North', 'Mar', 56
        UNION ALL SELECT 'South', 'Jan', 52
        UNION ALL SELECT 'South', 'Feb', 68
        UNION ALL SELECT 'South', 'Mar', 61
        UNION ALL SELECT 'East', 'Jan', 47
        UNION ALL SELECT 'East', 'Feb', 57
        UNION ALL SELECT 'East', 'Mar', 73
        UNION ALL SELECT 'West', 'Jan', 58
        UNION ALL SELECT 'West', 'Feb', 49
        UNION ALL SELECT 'West', 'Mar', 66
      `,
    },
  },
  waterfallRows: {
    qlConnectionId,
    data: {
      sql_query: `
        SELECT 1 AS sort_order, 'Starting pipeline' AS step_label, 140 AS delta_value, 'absolute' AS step_kind
        UNION ALL SELECT 2, 'Lead quality', -18, 'delta'
        UNION ALL SELECT 3, 'Retention uplift', 12, 'delta'
        UNION ALL SELECT 4, 'Sales enablement', 22, 'delta'
        UNION ALL SELECT 5, 'Final forecast', 156, 'absolute'
      `,
    },
  },
};
