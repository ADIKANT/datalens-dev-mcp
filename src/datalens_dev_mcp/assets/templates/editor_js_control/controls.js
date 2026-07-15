/*
 * Editor JS Control skeleton contract:
 * - Source/data contract: sources.js can provide dynamic option lists.
 * - Params/config: params.js owns selected defaults.
 * - Prepare/model normalization: controls.js emits native control definitions only.
 * - Render lifecycle: control_node renders natively, no custom HTML render.
 * - Layout/scales: labels stay left and width remains percentage-based.
 * - Labels/tooltips: label names the controlled field.
 * - Theme tokens: native controls inherit DataLens theme variables.
 * - Interactions: affected widgets are declared in dashboard relations.
 */
module.exports = {
  controls: [
    {
      type: 'select',
      param: 'segment',
      label: 'Segment',
      labelPlacement: 'left',
      width: '96%',
      multiselect: true,
      searchable: true,
      updateOnChange: true,
      content: [
        {title: 'All', value: 'all'},
        {title: 'New', value: 'new'},
      ],
    },
  ],
};
