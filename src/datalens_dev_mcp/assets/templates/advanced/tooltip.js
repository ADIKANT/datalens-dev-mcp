function esc(value) {
  return String(value == null ? '' : value).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

function renderTooltipShell({
  title,
  rows,
  comparisonMode = 'single_period',
  periodValueSource = 'normalized',
}) {
  const mode = comparisonMode === 'comparison' ? 'comparison' : 'single_period';
  if (periodValueSource !== 'normalized') {
    throw new Error('tooltip periodValueSource must be normalized');
  }
  const comparisonLabel = /^(?:vs|current|curr|comparison period|сравнение|текущ(?:ее|ий|ая)|период сравнения)$/i;
  const prepared = [];
  const seen = new Set();
  for (const sourceRow of rows || []) {
    const row = sourceRow || {};
    const role = String(row.role || '').trim().toLowerCase();
    const label = String(row.label || '').trim();
    const value = String(row.value == null ? '' : row.value).trim();
    const comparisonSpecific = ['vs', 'current', 'comparison_period'].includes(role) ||
      comparisonLabel.test(label);
    if (mode === 'single_period' && (role === 'vs' || role === 'comparison_period')) continue;
    if (mode === 'comparison' && role === 'comparison_period' && !value) continue;
    const displayLabel = mode === 'single_period' && comparisonSpecific
      ? String(row.metric_label || '').trim()
      : label;
    const key = `${role}|${displayLabel}|${value}`;
    if (seen.has(key)) continue;
    seen.add(key);
    prepared.push({label: displayLabel, value});
  }
  const body = prepared.map((row) => `<div style="display:flex;justify-content:space-between;gap:16px;margin-top:6px;"><span style="color:#667085;">${esc(row.label)}</span><b style="color:#111827;">${esc(row.value)}</b></div>`).join('');
  // DataLens owns the single popup container. This helper returns content only,
  // so nested borders, radii, and duplicate tooltip shells cannot appear.
  return `<div data-tooltip-container-owner="native" data-tooltip-comparison-mode="${mode}" data-tooltip-period-source="normalized" style="min-width:180px;max-width:340px;padding:10px 12px;background:transparent;border:0;border-radius:0;outline:none;font-family:Inter,Arial,sans-serif;color:#111827;font-size:12px;line-height:16px;"><div style="font-weight:800;">${esc(title)}</div>${body}</div>`;
}

module.exports = {renderTooltipShell};
