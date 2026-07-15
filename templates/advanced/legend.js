function esc(value) {
  return String(value == null ? '' : value).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

function renderLegendItems(items) {
  if (!items || items.length <= 1) return '';
  return `<div style="display:flex;gap:12px;flex-wrap:wrap;font-size:12px;line-height:14px;color:#667085;">${items.map((item) => `<span style="display:inline-flex;align-items:center;gap:6px;"><i style="width:9px;height:9px;background:${esc(item.color || '#2B75E2')};display:inline-block;"></i>${esc(item.label)}</span>`).join('')}</div>`;
}

function renderInlineShareLegend(items) {
  if (!items || !items.length) return '';
  return `<div style="display:flex;gap:10px;flex-wrap:wrap;font-size:11px;line-height:14px;color:#667085;">${items.map((item) => `<span style="display:inline-flex;align-items:center;gap:5px;"><i style="width:8px;height:8px;background:${esc(item.color || '#2B75E2')};display:inline-block;"></i>${esc(item.label)} ${esc(item.shareText || '')}</span>`).join('')}</div>`;
}

module.exports = {renderInlineShareLegend, renderLegendItems};
