function getPreparedLoadedData(loadedData, sourceName) {
  const sourceData = loadedData[sourceName] || [];
  const metadata = sourceData.find((item) => item.event === 'metadata');
  const names = (metadata && metadata.data && metadata.data.names) || [];
  return sourceData
    .filter((item) => item.event === 'row')
    .slice(0, 120)
    .map((item) => {
      const row = {};
      (item.data || []).forEach((value, index) => {
        row[names[index] || `column_${index + 1}`] = value;
      });
      return row;
    });
}

const rows = getPreparedLoadedData(Editor.getLoadedData(), 'tableRows');
const model = {
  title: 'Release Version Matrix',
  help: 'Rare Advanced table example for grouped headers and sticky row labels. Prefer table_node unless this layout is explicitly required.',
  rows: rows.length ? rows : [
    {group_name: 'No data', item_name: 'Adjust sources.js', current_version: '', target_version: '', release_state: 'unavailable'},
  ],
};

module.exports = {
  render: Editor.wrapFn({
    args: [model],
    fn: function(options, payload) {
      function escapeHtml(value) {
        return String(value == null ? '' : value)
          .replace(/&/g, '&amp;')
          .replace(/</g, '&lt;')
          .replace(/>/g, '&gt;')
          .replace(/"/g, '&quot;');
      }

      function stateColor(value) {
        const normalized = String(value || '').toLowerCase();
        if (normalized === 'blocked') return '#B42318';
        if (normalized === 'review') return '#B54708';
        if (normalized === 'ready') return '#027A48';
        return '#667085';
      }

      const body = payload.rows.map((row) => `
        <tr>
          <th style="position:sticky;left:0;background:#FFFFFF;text-align:left;padding:8px 10px;border-bottom:1px solid #EAECF0;color:#111827;font-size:12px;">${escapeHtml(row.group_name)}</th>
          <td style="padding:8px 10px;border-bottom:1px solid #EAECF0;color:#344054;font-size:12px;">${escapeHtml(row.item_name)}</td>
          <td style="padding:8px 10px;border-bottom:1px solid #EAECF0;color:#344054;font-size:12px;font-variant-numeric:tabular-nums;">${escapeHtml(row.current_version)}</td>
          <td style="padding:8px 10px;border-bottom:1px solid #EAECF0;color:#344054;font-size:12px;font-variant-numeric:tabular-nums;">${escapeHtml(row.target_version)}</td>
          <td style="padding:8px 10px;border-bottom:1px solid #EAECF0;color:${stateColor(row.release_state)};font-size:12px;font-weight:700;">${escapeHtml(row.release_state)}</td>
        </tr>
      `).join('');

      return Editor.generateHtml(`
        <section style="font-family:Inter,Arial,sans-serif;color:#111827;line-height:1.35;padding:12px 14px;overflow:auto;">
          <div style="display:flex;align-items:flex-start;justify-content:space-between;gap:12px;margin-bottom:10px;">
            <div>
              <h3 style="margin:0;font-size:15px;line-height:1.25;font-weight:800;">${escapeHtml(payload.title)}</h3>
              <p style="margin:4px 0 0;font-size:12px;color:#667085;max-width:720px;">${escapeHtml(payload.help)}</p>
            </div>
          </div>
          <table style="border-collapse:separate;border-spacing:0;width:100%;min-width:720px;">
            <thead>
              <tr>
                <th rowspan="2" style="position:sticky;left:0;background:#F8FAFC;text-align:left;padding:8px 10px;border-bottom:1px solid #D0D5DD;color:#475467;font-size:11px;">Group</th>
                <th rowspan="2" style="text-align:left;padding:8px 10px;border-bottom:1px solid #D0D5DD;color:#475467;font-size:11px;">Item</th>
                <th colspan="2" style="text-align:center;padding:6px 10px;border-bottom:1px solid #EAECF0;color:#475467;font-size:11px;">Version</th>
                <th rowspan="2" style="text-align:left;padding:8px 10px;border-bottom:1px solid #D0D5DD;color:#475467;font-size:11px;">State</th>
              </tr>
              <tr>
                <th style="text-align:left;padding:6px 10px;border-bottom:1px solid #D0D5DD;color:#475467;font-size:11px;">Current</th>
                <th style="text-align:left;padding:6px 10px;border-bottom:1px solid #D0D5DD;color:#475467;font-size:11px;">Target</th>
              </tr>
            </thead>
            <tbody>${body}</tbody>
          </table>
        </section>
      `);
    },
  }),
};
