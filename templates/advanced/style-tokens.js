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
    sm: 8,
    md: 12,
    lg: 16,
  },
  radius: {
    chip: 999,
  },
};

module.exports = {HOUSE_STYLE, STYLE_GUIDE};
