/* Canonical synthetic-safe KPI renderer. Bindings and labels arrive through config, not generated code. */
module.exports = function renderKpi(data, config) {
  const state = data && data.state ? data.state : 'no_data';
  return {
    type: 'kpi-sparkline',
    state,
    value: state === 'ready' || state === 'business_zero' ? data.value : null,
    comparison: data ? data.comparison : null,
    sparkline: data && Array.isArray(data.points) ? data.points : [],
    title: config.visible_title,
    hint: config.hint,
    tooltip: config.tooltip,
    theme: config.states_theme.theme
  };
};
