function esc(value) {
  return String(value == null ? '' : value).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

function renderTooltipShell({title, rows}) {
  const body = (rows || []).map((row) => `<div style="display:flex;justify-content:space-between;gap:16px;margin-top:6px;"><span style="color:#667085;">${esc(row.label)}</span><b style="color:#111827;">${esc(row.value)}</b></div>`).join('');
  return `<div style="min-width:180px;max-width:340px;padding:10px 12px;background:#FFFFFF;border-radius:8px;border:1px solid #E5E7EB;font-family:Inter,Arial,sans-serif;color:#111827;font-size:12px;line-height:16px;"><div style="font-weight:800;">${esc(title)}</div>${body}</div>`;
}

module.exports = {renderTooltipShell};
