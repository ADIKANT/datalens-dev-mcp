function esc(value) {
  return String(value == null ? '' : value).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

function renderSourceFreshness({sourceLabel, freshnessLabel, updatedAt}) {
  const source = esc(sourceLabel || 'Source');
  const freshness = esc(freshnessLabel || 'Updated');
  const updated = esc(updatedAt || 'n/a');
  return `<div style="font-size:11px;line-height:14px;color:#98A2B3;font-weight:700;">${source} · ${freshness}: ${updated}</div>`;
}

module.exports = {renderSourceFreshness};
