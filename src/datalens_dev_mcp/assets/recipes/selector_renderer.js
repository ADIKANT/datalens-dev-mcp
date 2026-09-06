/* Canonical selector renderer. It never invents reset behavior or consumers. */
module.exports = function renderSelector(options, config) {
  return {
    type: 'selector',
    state: Array.isArray(options) && options.length ? 'ready' : 'no_options',
    options: Array.isArray(options) ? options.map(String) : [],
    parameter: config.selector,
    geometry: config.geometry
  };
};
