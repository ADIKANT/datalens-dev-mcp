/* DataLens Controls contract. Current selection belongs to the linked param. */
module.exports = function renderSelector(options, config) {
  const selector = config.selector;
  const controls = [{
    type: 'select',
    param: selector.param_name,
    content: options.map(option => ({title: option.title, value: option.value})),
    multiselect: selector.mode === 'multi',
    searchable: true,
    required: !selector.clear,
    updateOnChange: true,
    width: '100%',
    label: config.visible_title.owner === 'body' && config.visible_title.visible
      ? config.visible_title.text : ''
  }];
  if (selector.reset) {
    controls.push({type: 'button', label: 'Reset', onClick: {action: 'setInitialParams'}});
  }
  return {controls};
};
