module.exports = {
  updateControlsOnChange: true,
  controls: [
    {
      type: 'select',
      param: 'compare_mode',
      label: 'Compare',
      labelPlacement: 'left',
      updateOnChange: true,
      content: [
        {title: 'None', value: 'none'},
        {title: 'Previous period', value: 'previous_period'},
        {title: 'Target', value: 'target'},
      ],
    },
  ],
};
