const {HOUSE_STYLE} = require('./style-tokens');

function escapeHtml(value) {
  return String(value == null ? '' : value)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function renderAdvancedFrame({title, hint, body, width = 640, height = 360, extraHeader = ''}) {
  return `
    <div style="box-sizing:border-box;width:${width}px;height:${height}px;padding:12px 16px;background:transparent;border:none;font-family:Inter,Arial,sans-serif;color:${HOUSE_STYLE.colors.text.strong};display:flex;flex-direction:column;gap:10px;overflow:hidden;">
      <div style="display:flex;align-items:center;gap:8px;min-width:0;">
        <div style="font-size:18px;line-height:20px;font-weight:800;letter-spacing:0.08em;text-transform:uppercase;color:#5F6368;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">${escapeHtml(title)}</div>
        <span data-id="hint" title="${escapeHtml(hint || title)}" style="display:inline-flex;align-items:center;justify-content:center;width:18px;height:18px;border-radius:999px;background:#F3F4F6;color:#5F6368;font-size:11px;font-weight:800;">?</span>
        ${extraHeader}
      </div>
      <div style="flex:1;min-height:0;overflow:hidden;">${body}</div>
    </div>
  `;
}

module.exports = {renderAdvancedFrame};
