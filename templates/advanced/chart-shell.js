const {HOUSE_STYLE} = require('./style-tokens');

function escapeHtml(value) {
  return String(value == null ? '' : value)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function renderAdvancedFrame({title, hint, body, width = 640, height = 360, extraHeader = ''}) {
  const compact = width < 720;
  const shellY = compact ? HOUSE_STYLE.spacing.shellCompactY : HOUSE_STYLE.spacing.shellY;
  const shellX = compact ? HOUSE_STYLE.spacing.shellCompactX : HOUSE_STYLE.spacing.shellX;
  const stackGap = compact ? HOUSE_STYLE.spacing.stackCompact : HOUSE_STYLE.spacing.stack;
  const titleType = compact ? HOUSE_STYLE.typography.chartTitleCompact : HOUSE_STYLE.typography.chartTitle;
  return `
    <div data-render-density="${compact ? 'compact' : 'comfortable'}" style="box-sizing:border-box;width:${width}px;height:${height}px;padding:${shellY}px ${shellX}px;background:transparent;border:0;border-radius:0;outline:none;font-family:${HOUSE_STYLE.typography.family};color:${HOUSE_STYLE.colors.text.strong};display:flex;flex-direction:column;gap:${stackGap}px;overflow:hidden;">
      <div style="display:flex;align-items:center;gap:8px;min-width:0;">
        <div style="font-size:${titleType.fontSize}px;line-height:${titleType.lineHeight}px;font-weight:${titleType.fontWeight};color:#5F6368;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">${escapeHtml(title)}</div>
        <span data-id="hint" title="${escapeHtml(hint || title)}" style="display:inline-flex;align-items:center;justify-content:center;width:18px;height:18px;border-radius:999px;background:#F3F4F6;color:#5F6368;font-size:11px;font-weight:800;">?</span>
        ${extraHeader}
      </div>
      <div style="flex:1;min-height:0;overflow:hidden;">${body}</div>
    </div>
  `;
}

module.exports = {renderAdvancedFrame};
