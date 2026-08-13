/**
 * Готовая конфигурация контролов и их связи с Params.
 * Route: editor_js_control. Технические имена параметров и aliases оставлены без перевода.
 */
const __DL_RENDER_CONTRACT = Object.freeze({"adapter_ids":["selector_rows"],"adapters":{"selector_rows":{"allowed_tooltip_owners":["native"],"tokens":{"component":{"kind":"selector_row"},"selector":{"apply_button":false,"control_max_width_percent":94,"update_mode":"immediate"}}}},"composite_sha256":"c00cacad2cd385e6ca6b5688cd0704fd9f0583a6fbbcc1a12ef0fd1ab07f3140","core":{"comparison_context":{"duplicate_chart_captions":false,"height_policy":"content_lines_1_to_3","max_blocks":1,"minimum_height_px":24,"placement":"below_selectors","required_fields":["method","selected_range","comparison_range"],"required_when_comparison_enabled":true,"semantic_line_count":1},"dashboard_composition":{"desktop_grid_columns":36,"equal_height_within_semantic_row":true,"gap_after_default":0,"kpi_height_units":{"compact":6,"sparkline":8},"kpi_max_per_row":3,"kpi_width_units":12,"schema_id":"dashboard_composition","selector_height_units":{"one_row":2,"two_rows":3},"selector_row_width_percent":94},"density":{"active_variant":"viewport","compact_below_width_px":720,"mode":"responsive"},"kpi":{"content":{"value_marker":"kpi-value","value_must_be_visible":true,"value_required":true},"label_typography":{"font_size_px":12,"line_height_px":15},"layout":{"equal_height_within_kpi_set":true,"runtime_policy":"content_visible_without_clipping","update_policy":"preserve_fresh_saved_geometry"},"padding_px":{"bottom":7,"left":11,"right":11,"top":11},"sparkline_policy":"all_or_none_within_dashboard_kpi_set","surface":{"background":"transparent","border":{"style":"none","width_px":0},"outline":{"style":"none","width_px":0},"radius_px":0,"shadow":"none"},"value_typography":{"compact":{"font_size_px":31,"line_height_px":34},"font_weight":750,"normal":{"font_size_px":34,"line_height_px":38}}},"layout_grid":{"equal_height_within_semantic_row":true,"native_height_units":{"comparison_context_maximum":3,"comparison_context_minimum":1,"kpi_compact_default":6,"kpi_creation_default":8,"selector_creation_default":2,"selector_two_row_default":3,"title_creation_default":2},"overflow_policy":"expand_or_scroll_never_clip","runtime_relation":"measured_independently_from_native_units","update_policy":"preserve_fresh_saved_geometry"},"number_format":{"decimal_separator":"comma","group_separator":"nbsp"},"plot_area":{"applies_to":"coordinate_plot_area","inset_px":{"bottom":34,"left":"family_axis_owned","right":{"compact":10,"normal":16},"top":22}},"selector":{"apply_button":false,"blank_multiselect_semantics":"all","control_max_width_percent":94,"label_placement":"left","period_first_if_present":true,"row_height_px":44,"row_target_width_percent":94,"row_width_tolerance_percent":0,"single_row":false,"update_mode":"immediate"},"semantic_colors":{"comparison":"#8A919C","failure":"#E57373","primary":"#2B75E2","success":"#6CBF84"},"series_visibility":{"filtered_out_series":"omit","identity":"series_key","legend":"active_series_only","marks":"active_series_only","source":"filtered_result_rows","tooltip":"active_series_only","zero_only_unfiltered_series":"preserve"},"shell":{"gap_px":{"compact":7,"normal":9},"padding_px":{"compact":{"horizontal":10,"vertical":9},"normal":{"horizontal":13,"vertical":11}}},"title_contract":{"modes":["embedded_title","content_label","tab_only","native_title","tab_strip"],"native_and_runtime_mutually_exclusive":true,"schema_id":"dashboard_title_contract"},"tooltip":{"comparison_adaptive":true,"empty_comparison_period_forbidden":true,"max_width_px":340,"owner":"native","padding_px":{"horizontal":12,"vertical":10},"period_value_source":"normalized","redundant_row_title":false,"show_comparison_period_only_when_comparison":true,"show_current_label_only_when_comparison":true,"show_vs_separator_only_when_comparison":true,"surface":{"border":{"style":"none","width_px":0},"outline":{"style":"none","width_px":0},"radius_px":0,"shadow":"none"}},"typography":{"axis":{"font_size_px":12,"line_height_px":16},"body":{"font_size_px":12,"line_height_px":16},"font_family":["Inter","Arial","sans-serif"],"legend":{"compact":{"font_size_px":12,"line_height_px":16},"default":{"font_size_px":12,"line_height_px":16},"readable":{"font_size_px":14,"line_height_px":18}},"table":{"font_size_px":12,"line_height_px":17},"title":{"compact":{"font_size_px":16,"line_height_px":20},"normal":{"font_size_px":17,"line_height_px":21}},"tooltip":{"font_size_px":12,"line_height_px":16}},"viewport":{"compact_below_width_px":720,"min_height_px":160,"min_width_px":280}},"effective_tokens":{"comparison_context":{"duplicate_chart_captions":false,"height_policy":"content_lines_1_to_3","max_blocks":1,"minimum_height_px":24,"placement":"below_selectors","required_fields":["method","selected_range","comparison_range"],"required_when_comparison_enabled":true,"semantic_line_count":1},"component":{"kind":"selector_row"},"dashboard_composition":{"desktop_grid_columns":36,"equal_height_within_semantic_row":true,"gap_after_default":0,"kpi_height_units":{"compact":6,"sparkline":8},"kpi_max_per_row":3,"kpi_width_units":12,"schema_id":"dashboard_composition","selector_height_units":{"one_row":2,"two_rows":3},"selector_row_width_percent":94},"density":{"active_variant":"viewport","compact_below_width_px":720,"mode":"responsive"},"kpi":{"content":{"value_marker":"kpi-value","value_must_be_visible":true,"value_required":true},"label_typography":{"font_size_px":12,"line_height_px":15},"layout":{"equal_height_within_kpi_set":true,"runtime_policy":"content_visible_without_clipping","update_policy":"preserve_fresh_saved_geometry"},"padding_px":{"bottom":7,"left":11,"right":11,"top":11},"sparkline_policy":"all_or_none_within_dashboard_kpi_set","surface":{"background":"transparent","border":{"style":"none","width_px":0},"outline":{"style":"none","width_px":0},"radius_px":0,"shadow":"none"},"value_typography":{"compact":{"font_size_px":31,"line_height_px":34},"font_weight":750,"normal":{"font_size_px":34,"line_height_px":38}}},"layout_grid":{"equal_height_within_semantic_row":true,"native_height_units":{"comparison_context_maximum":3,"comparison_context_minimum":1,"kpi_compact_default":6,"kpi_creation_default":8,"selector_creation_default":2,"selector_two_row_default":3,"title_creation_default":2},"overflow_policy":"expand_or_scroll_never_clip","runtime_relation":"measured_independently_from_native_units","update_policy":"preserve_fresh_saved_geometry"},"number_format":{"decimal_separator":"comma","group_separator":"nbsp"},"plot_area":{"applies_to":"coordinate_plot_area","inset_px":{"bottom":34,"left":"family_axis_owned","right":{"compact":10,"normal":16},"top":22}},"selector":{"apply_button":false,"blank_multiselect_semantics":"all","control_max_width_percent":94,"label_placement":"left","period_first_if_present":true,"row_height_px":44,"row_target_width_percent":94,"row_width_tolerance_percent":0,"single_row":false,"update_mode":"immediate"},"semantic_colors":{"comparison":"#8A919C","failure":"#E57373","primary":"#2B75E2","success":"#6CBF84"},"series_visibility":{"filtered_out_series":"omit","identity":"series_key","legend":"active_series_only","marks":"active_series_only","source":"filtered_result_rows","tooltip":"active_series_only","zero_only_unfiltered_series":"preserve"},"shell":{"gap_px":{"compact":7,"normal":9},"padding_px":{"compact":{"horizontal":10,"vertical":9},"normal":{"horizontal":13,"vertical":11}}},"title_contract":{"modes":["embedded_title","content_label","tab_only","native_title","tab_strip"],"native_and_runtime_mutually_exclusive":true,"schema_id":"dashboard_title_contract"},"tooltip":{"comparison_adaptive":true,"empty_comparison_period_forbidden":true,"max_width_px":340,"owner":"native","padding_px":{"horizontal":12,"vertical":10},"period_value_source":"normalized","redundant_row_title":false,"show_comparison_period_only_when_comparison":true,"show_current_label_only_when_comparison":true,"show_vs_separator_only_when_comparison":true,"surface":{"border":{"style":"none","width_px":0},"outline":{"style":"none","width_px":0},"radius_px":0,"shadow":"none"}},"typography":{"axis":{"font_size_px":12,"line_height_px":16},"body":{"font_size_px":12,"line_height_px":16},"font_family":["Inter","Arial","sans-serif"],"legend":{"active":{"font_size_px":12,"line_height_px":16},"active_token":"legend.default","compact":{"font_size_px":12,"line_height_px":16},"default":{"font_size_px":12,"line_height_px":16},"readable":{"font_size_px":14,"line_height_px":18}},"table":{"font_size_px":12,"line_height_px":17},"title":{"compact":{"font_size_px":16,"line_height_px":20},"normal":{"font_size_px":17,"line_height_px":21}},"tooltip":{"font_size_px":12,"line_height_px":16}},"viewport":{"compact_below_width_px":720,"min_height_px":160,"min_width_px":280}},"family":"selector_group","overrides":{},"profile_id":"standard_dashboard","profile_sha256":"70fb8647e0ed8fe5f6f8dbab1f4aceda07b780e73de1a1c9cee55cb07ce41135","registry_sha256":"39cdac0e2e5eedf0dedda2631d127344f3e471cac311851293f48d5c021e1de8","schema_id":"dashboard_render_profiles"});

const loaded = Editor.getLoadedData();

function preparedRows(source) {
  if (Array.isArray(source)) {
    const names = source.find((item) => item && item.event === 'metadata')?.data?.names || [];
    return source.filter((item) => item && item.event === 'row' && Array.isArray(item.data))
      .map((item) => Object.fromEntries(item.data.map((value, index) => [names[index] || `column_${index + 1}`, value])));
  }
  const result = source?.result || {};
  const rows = result.data?.Data || [];
  const fields = result.fields || [];
  const names = fields.map((field, index) => String(field.title || field.guid || index));
  return rows.map((row) => Object.fromEntries(row.map((value, index) => [names[index] || `column_${index + 1}`, value])));
}

function selectorOptions(sourceName, valueField) {
  const seen = new Set();
  return preparedRows(loaded[sourceName] || []).flatMap((row) => {
    const value = String(row?.[valueField] ?? '');
    if (!value || seen.has(value)) return [];
    seen.add(value);
    return [{title: value, value}];
  });
}

module.exports = {
  controls: [
    {
      type: 'range-datepicker',
      paramFrom: "dateFrom",
      paramTo: "dateTo",
      label: "Период",
      labelPlacement: 'left',
      width: '47%',
      updateOnИзменение: true,
    },
    {
      type: 'select',
      param: "status",
      label: "Статус",
      labelPlacement: 'left',
      width: '47%',
      updateOnИзменение: true,
      multiselect: false,
      searchable: false,
      content: [{"title": "Все", "value": "all"}, {"title": "Открыт", "value": "open"}, {"title": "Готово", "value": "done"}],
    },
    {
      type: 'select',
      param: "segment",
      label: "Сегмент",
      labelPlacement: 'left',
      width: '94%',
      updateOnИзменение: true,
      multiselect: false,
      searchable: true,
      content: selectorOptions("rows", "value"),
    },
  ],
};
