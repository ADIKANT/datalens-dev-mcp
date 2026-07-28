// Theme tokens: shared light/dark semantic colors for helper snippets.
// Keep route-specific emphasis in params/config; avoid one-off palettes in chart bodies.
const STYLE_GUIDE = {
  light: {
    surface: {
      base: 'var(--g-color-base-background, #FFFFFF)',
      muted: 'var(--g-color-base-neutral-light, #F8FAFC)',
      border: 'var(--g-color-line-generic, #E5E7EB)',
    },
    text: {
      strong: 'var(--g-color-text-primary, #111827)',
      muted: 'var(--g-color-text-secondary, #667085)',
      subtle: 'var(--g-color-text-hint, #98A2B3)',
    },
  },
  dark: {
    surface: {
      base: 'var(--g-color-base-background, #111827)',
      muted: 'var(--g-color-base-neutral-light, #1F2937)',
      border: 'var(--g-color-line-generic, #374151)',
    },
    text: {
      strong: 'var(--g-color-text-primary, #F9FAFB)',
      muted: 'var(--g-color-text-secondary, #D1D5DB)',
      subtle: 'var(--g-color-text-hint, #9CA3AF)',
    },
  },
};

const HOUSE_STYLE = {
  colors: {
    surface: STYLE_GUIDE.light.surface,
    text: STYLE_GUIDE.light.text,
    data: {
      primary: '#2B75E2',
      accent: '#6A8FCA',
      secondary: '#8BB7A2',
      other: '#A8B0BD',
      muted: '#D7E3F6',
    },
    semantic: {
      ok: '#237A57',
      warning: '#B7791F',
      critical: '#B42318',
      neutral: '#5F6368',
      unavailable: '#667085',
    },
  },
  themes: STYLE_GUIDE,
  spacing: {
    xs: 4,
    shellCompactY: 9,
    shellCompactX: 10,
    shellY: 11,
    shellX: 13,
    stackCompact: 7,
    stack: 9,
    sm: 8,
    md: 12,
    lg: 16,
  },
  typography: {
    family: 'Inter,Arial,sans-serif',
    body: {fontSize: 12, lineHeight: 16},
    axis: {fontSize: 12, lineHeight: 16},
    legend: {fontSize: 12, lineHeight: 16},
    tooltip: {fontSize: 12, lineHeight: 16},
    chartTitleCompact: {fontSize: 16, lineHeight: 20, fontWeight: 800},
    chartTitle: {fontSize: 17, lineHeight: 21, fontWeight: 800},
    kpiLabel: {fontSize: 12, lineHeight: 15, fontWeight: 800},
    kpiValueCompact: {fontSize: 31, lineHeight: 34, fontWeight: 750},
    kpiValue: {fontSize: 34, lineHeight: 38, fontWeight: 750},
    table: {fontSize: 12, lineHeight: 17},
  },
  surfaces: {
    kpi: {
      background: 'transparent',
      border: 0,
      borderRadius: 0,
      outline: 'none',
      boxShadow: 'none',
      padding: [11, 11, 7, 11],
      gap: 5,
    },
    tooltip: {
      containerOwner: 'native',
      border: 0,
      borderRadius: 0,
      padding: [10, 12],
      maxWidth: 340,
    },
  },
  radius: {
    chip: 999,
  },
};

module.exports = {HOUSE_STYLE, STYLE_GUIDE};
