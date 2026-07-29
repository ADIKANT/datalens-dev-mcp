function esc(value) {
  return String(value == null ? '' : value).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

function renderLegendItems(items) {
  const activeItems = (items || []).filter((item) => item && item.active !== false);
  if (activeItems.length <= 1) return '';
  return `<div data-role="legend" data-series-source="filtered-result-rows" style="display:flex;column-gap:14px;row-gap:7px;flex-wrap:wrap;font-size:12px;line-height:16px;color:#667085;">${activeItems.map((item) => `<span data-series-id="${esc(item.seriesKey || item.id || item.label)}" data-series-role="legend" style="display:inline-flex;align-items:center;gap:6px;"><i style="width:10px;height:7px;background:${esc(item.color || '#2B75E2')};display:inline-block;"></i>${esc(item.label)}</span>`).join('')}</div>`;
}

function renderInlineShareLegend(items) {
  const activeItems = (items || []).filter((item) => item && item.active !== false);
  if (!activeItems.length) return '';
  return `<div data-role="legend" data-series-source="filtered-result-rows" style="display:flex;column-gap:14px;row-gap:7px;flex-wrap:wrap;font-size:12px;line-height:16px;color:#667085;">${activeItems.map((item) => `<span data-series-id="${esc(item.seriesKey || item.id || item.label)}" data-series-role="legend" style="display:inline-flex;align-items:center;gap:6px;"><i style="width:10px;height:7px;background:${esc(item.color || '#2B75E2')};display:inline-block;"></i>${esc(item.label)} ${esc(item.shareText || '')}</span>`).join('')}</div>`;
}

module.exports = {renderInlineShareLegend, renderLegendItems};
