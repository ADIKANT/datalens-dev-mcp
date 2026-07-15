// Theme tokens: shared semantic colors, spacing, and radii for every Advanced Editor template.
// Keep dashboard-specific emphasis in params/config; do not introduce ad hoc palettes in prepare.js.
const STYLE_GUIDE = {
  light: {
    colors: {
      surface: 'var(--g-color-base-background, #FFFFFF)',
      surfaceMuted: 'var(--g-color-base-neutral-light, #F8FAFC)',
      border: 'var(--g-color-line-generic, #E5E7EB)',
      gridLine: 'var(--g-color-line-generic, #E5E7EB)',
      text: 'var(--g-color-text-primary, #111827)',
      textMuted: 'var(--g-color-text-secondary, #667085)',
      textSubtle: 'var(--g-color-text-hint, #98A2B3)',
      tooltipBackground: 'var(--g-color-base-float, #FFFFFF)',
      tooltipText: 'var(--g-color-text-primary, #111827)',
      primary: '#2B75E2',
      accent: '#2B75E2',
      ok: 'var(--g-color-text-positive, #237A57)',
      warning: 'var(--g-color-text-warning, #B7791F)',
      critical: 'var(--g-color-text-danger, #B42318)',
      category: ['#2B75E2', '#6A8FCA', '#8BB7A2', '#A8B0BD', '#D4A95F', '#B58CCF'],
      sequential: ['#D7E3F6', '#AFC7ED', '#7AA7F0', '#2B75E2'],
      tableHeader: 'var(--g-color-base-neutral-light, transparent)',
      tableRow: 'var(--g-color-base-background, transparent)',
      selectorLabel: 'var(--g-color-text-secondary, #667085)',
    },
    chart_categorical_palette: ['#2B75E2', '#6A8FCA', '#8BB7A2', '#A8B0BD', '#D4A95F', '#B58CCF'],
    table_header_background: 'var(--g-color-base-neutral-light, transparent)',
  },
  dark: {
    colors: {
      surface: 'var(--g-color-base-background, #111827)',
      surfaceMuted: 'var(--g-color-base-neutral-light, #1F2937)',
      border: 'var(--g-color-line-generic, #374151)',
      gridLine: 'var(--g-color-line-generic, #374151)',
      text: 'var(--g-color-text-primary, #F9FAFB)',
      textMuted: 'var(--g-color-text-secondary, #D1D5DB)',
      textSubtle: 'var(--g-color-text-hint, #9CA3AF)',
      tooltipBackground: 'var(--g-color-base-float, #1F2937)',
      tooltipText: 'var(--g-color-text-primary, #F9FAFB)',
      primary: '#79A8F7',
      accent: '#79A8F7',
      ok: 'var(--g-color-text-positive, #5BD18B)',
      warning: 'var(--g-color-text-warning, #F2B84B)',
      critical: 'var(--g-color-text-danger, #F87171)',
      category: ['#79A8F7', '#9FB9E5', '#A8CDB9', '#B7BEC8', '#E0C47C', '#C9A6DF'],
      sequential: ['#1F2937', '#385A8D', '#5D85C9', '#79A8F7'],
      tableHeader: 'var(--g-color-base-neutral-light, transparent)',
      tableRow: 'var(--g-color-base-background, transparent)',
      selectorLabel: 'var(--g-color-text-secondary, #D1D5DB)',
    },
    chart_categorical_palette: ['#79A8F7', '#9FB9E5', '#A8CDB9', '#B7BEC8', '#E0C47C', '#C9A6DF'],
    table_header_background: 'var(--g-color-base-neutral-light, transparent)',
  },
};

const HOUSE_STYLE = {
  colors: STYLE_GUIDE.light.colors,
  themes: STYLE_GUIDE,
  radius: 6,
  spacing: 12,
};

module.exports = {HOUSE_STYLE, STYLE_GUIDE};
