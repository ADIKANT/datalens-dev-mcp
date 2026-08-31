/**
 * Ready control configuration and Params bindings.
 * Route: editor_js_control. Technical parameter names and aliases are language-neutral.
 */
const __DL_RENDER_CONTRACT = Object.freeze({"adapter_ids":["selector_rows"],"adapters":{"selector_rows":{"allowed_tooltip_owners":["native"],"tokens":{"component":{"kind":"selector_row"},"selector":{"apply_button":false,"update_mode":"immediate"}}}},"composite_sha256":"2a46b33c5ffc53c1dcb1d1b2bc42b8225c45c0b30102ed1f855795f2546be9df","core":{"comparison_context":{"duplicate_chart_captions":false,"height_policy":"content_lines_1_to_3","max_blocks":1,"minimum_height_px":24,"required_fields":["method","selected_range","comparison_range"],"required_when_comparison_enabled":true,"semantic_line_count":1},"dashboard_composition":{"desktop_grid_columns":36,"equal_height_within_semantic_row":true,"gap_after_default":0,"schema_id":"dashboard_composition"},"density":{"active_variant":"viewport","compact_below_width_px":720,"mode":"responsive"},"kpi":{"content":{"value_marker":"kpi-value","value_must_be_visible":true,"value_required":true},"label_typography":{"font_size_px":12,"line_height_px":15},"layout":{"equal_height_within_kpi_set":true,"runtime_policy":"content_visible_without_clipping","update_policy":"preserve_fresh_saved_geometry"},"padding_px":{"bottom":7,"left":11,"right":11,"top":11},"sparkline_policy":"all_or_none_within_dashboard_kpi_set","value_typography":{"compact":{"font_size_px":31,"line_height_px":34},"font_weight":750,"normal":{"font_size_px":34,"line_height_px":38}}},"layout_grid":{"equal_height_within_semantic_row":true,"overflow_policy":"expand_or_scroll_never_clip","runtime_relation":"measured_independently_from_native_units","update_policy":"preserve_fresh_saved_geometry"},"number_format":{"decimal_separator":"comma","group_separator":"nbsp"},"plot_area":{"applies_to":"coordinate_plot_area","inset_px":{"bottom":34,"left":"family_axis_owned","right":{"compact":10,"normal":16},"top":22}},"selector":{"apply_button":false,"update_mode":"immediate"},"semantic_colors":{"comparison":"#8A919C","failure":"#E57373","primary":"#2B75E2","success":"#6CBF84"},"series_visibility":{"filtered_out_series":"omit","identity":"series_key","legend":"active_series_only","marks":"active_series_only","source":"filtered_result_rows","tooltip":"active_series_only","zero_only_unfiltered_series":"preserve"},"shell":{"gap_px":{"compact":7,"normal":9},"padding_px":{"compact":{"horizontal":10,"vertical":9},"normal":{"horizontal":13,"vertical":11}}},"title_contract":{"modes":["embedded_title","content_label","tab_only","native_title","tab_strip"],"native_and_runtime_mutually_exclusive":true,"schema_id":"dashboard_title_contract"},"tooltip":{"comparison_adaptive":true,"empty_comparison_period_forbidden":true,"owner":"native","period_value_source":"normalized","show_comparison_period_only_when_comparison":true,"show_current_label_only_when_comparison":true,"show_vs_separator_only_when_comparison":true},"typography":{"axis":{"font_size_px":12,"line_height_px":16},"body":{"font_size_px":12,"line_height_px":16},"font_family":["Inter","Arial","sans-serif"],"table":{"font_size_px":12,"line_height_px":17},"title":{"compact":{"font_size_px":16,"line_height_px":20},"normal":{"font_size_px":17,"line_height_px":21}},"tooltip":{"font_size_px":12,"line_height_px":16}},"viewport":{"compact_below_width_px":720,"min_height_px":160,"min_width_px":280}},"effective_tokens":{"comparison_context":{"duplicate_chart_captions":false,"height_policy":"content_lines_1_to_3","max_blocks":1,"minimum_height_px":24,"required_fields":["method","selected_range","comparison_range"],"required_when_comparison_enabled":true,"semantic_line_count":1},"component":{"kind":"selector_row"},"dashboard_composition":{"desktop_grid_columns":36,"equal_height_within_semantic_row":true,"gap_after_default":0,"schema_id":"dashboard_composition"},"density":{"active_variant":"viewport","compact_below_width_px":720,"mode":"responsive"},"kpi":{"content":{"value_marker":"kpi-value","value_must_be_visible":true,"value_required":true},"label_typography":{"font_size_px":12,"line_height_px":15},"layout":{"equal_height_within_kpi_set":true,"runtime_policy":"content_visible_without_clipping","update_policy":"preserve_fresh_saved_geometry"},"padding_px":{"bottom":7,"left":11,"right":11,"top":11},"sparkline_policy":"all_or_none_within_dashboard_kpi_set","value_typography":{"compact":{"font_size_px":31,"line_height_px":34},"font_weight":750,"normal":{"font_size_px":34,"line_height_px":38}}},"layout_grid":{"equal_height_within_semantic_row":true,"overflow_policy":"expand_or_scroll_never_clip","runtime_relation":"measured_independently_from_native_units","update_policy":"preserve_fresh_saved_geometry"},"number_format":{"decimal_separator":"comma","group_separator":"nbsp"},"plot_area":{"applies_to":"coordinate_plot_area","inset_px":{"bottom":34,"left":"family_axis_owned","right":{"compact":10,"normal":16},"top":22}},"selector":{"apply_button":false,"update_mode":"immediate"},"semantic_colors":{"comparison":"#8A919C","failure":"#E57373","primary":"#2B75E2","success":"#6CBF84"},"series_visibility":{"filtered_out_series":"omit","identity":"series_key","legend":"active_series_only","marks":"active_series_only","source":"filtered_result_rows","tooltip":"active_series_only","zero_only_unfiltered_series":"preserve"},"shell":{"gap_px":{"compact":7,"normal":9},"padding_px":{"compact":{"horizontal":10,"vertical":9},"normal":{"horizontal":13,"vertical":11}}},"title_contract":{"modes":["embedded_title","content_label","tab_only","native_title","tab_strip"],"native_and_runtime_mutually_exclusive":true,"schema_id":"dashboard_title_contract"},"tooltip":{"comparison_adaptive":true,"empty_comparison_period_forbidden":true,"owner":"native","period_value_source":"normalized","show_comparison_period_only_when_comparison":true,"show_current_label_only_when_comparison":true,"show_vs_separator_only_when_comparison":true},"typography":{"axis":{"font_size_px":12,"line_height_px":16},"body":{"font_size_px":12,"line_height_px":16},"font_family":["Inter","Arial","sans-serif"],"table":{"font_size_px":12,"line_height_px":17},"title":{"compact":{"font_size_px":16,"line_height_px":20},"normal":{"font_size_px":17,"line_height_px":21}},"tooltip":{"font_size_px":12,"line_height_px":16}},"viewport":{"compact_below_width_px":720,"min_height_px":160,"min_width_px":280}},"family":"selector_family_dynamic","overlay_ids":[],"overrides":{},"profile_id":"standard_dashboard","profile_sha256":"d02f86a0ea31b1d03d87fc734f58d166327ae7bdc0af8e33a29dbc921cf6a35d","registry_sha256":"c068d515bb5cbaa031fc728e6e49bd5ae6ea13b8118190eea18af0b3e85ab7f1","schema_id":"dashboard_render_profiles"});

const loaded = Editor.getLoadedData();

function preparedRows(source) {
  if (Array.isArray(source)) {
    const names = source.find((item) => item && item.event === 'metadata')?.data?.names || [];
    const eventRows = source.filter((item) => item && item.event === 'row' && Array.isArray(item.data));
    if (names.length && eventRows.length) {
      return eventRows.map((item) => Object.fromEntries(
        item.data.map((value, index) => [names[index] || `column_${index + 1}`, value]),
      ));
    }
    return source.filter((item) => item && typeof item === 'object' && !item.event);
  }
  const result = source?.result || {};
  const rawRows = result.data?.Data || [];
  const fields = result.fields || [];
  const names = fields.map((field, index) => String(field.title || field.guid || index));
  return rawRows.map((row) => Object.fromEntries(
    row.map((value, index) => [names[index] || `column_${index + 1}`, value]),
  ));
}
const rows = preparedRows(loaded.rows || []);
const seen = new Set();
const content = rows.flatMap((row) => {
  const value = String(row?.value ?? '');
  if (!value || seen.has(value)) return [];
  seen.add(value);
  const rawTitle = row?.title;
  return [{title: String(rawTitle ?? value), value}];
});

module.exports = {
  controls: [
    {
      type: 'select',
      param: "segment",
      label: "Segment",
      labelPlacement: 'left',
      width: '94%',
      updateOnChange: true,
      multiselect: false,
      searchable: true,
      content: content,
    },
  ],
};
