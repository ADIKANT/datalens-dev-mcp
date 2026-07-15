/*
 * Editor JS Control template contract:
 * - Source/data contract: sources.js may supply dynamic options; static options stay explicit here.
 * - Params/config: params.json owns default selected values and reset state.
 * - Prepare/model normalization: controls.js emits DataLens control definitions only.
 * - Render lifecycle: control_node is native; no custom HTML render is generated.
 * - Layout/scales: labels stay left and row widths are percentage-based.
 * - Labels/tooltips: labels describe the controlled field, while dashboard hints stay metadata.
 * - Theme tokens: native controls inherit DataLens light/dark theme variables.
 * - Interactions: affected widgets must be represented in dashboard selector relations.
 */
module.exports = {
  controls: [
    {
      type: 'select',
      param: 'status',
      label: 'Status',
      labelPlacement: 'left',
      width: '96%',
      multiselect: true,
      searchable: true,
      updateOnChange: true,
      content: [
        {title: 'All', value: 'all'},
        {title: 'Open', value: 'open'},
        {title: 'Done', value: 'done'},
      ],
    },
  ],
};
