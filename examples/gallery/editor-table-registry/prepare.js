function getPreparedLoadedData(loadedData, sourceName) {
  const sourceData = loadedData[sourceName] || [];
  const metadata = sourceData.find((item) => item.event === 'metadata');
  const names = metadata?.data?.names || [];
  return sourceData
    .filter((item) => item.event === 'row')
    .map((item) => {
      const row = {};
      (item.data || []).forEach((value, index) => {
        row[names[index] || `column_${index + 1}`] = value;
      });
      return row;
    });
}

const limit = Number(Editor.getParams().rowLimit?.[0] || 200);
const sourceRows = getPreparedLoadedData(Editor.getLoadedData(), 'rows').slice(0, limit);
const tableRows = sourceRows.length ? sourceRows : [{status: 'No data', item: 'Adjust sources.js', value: 0}];

const head = [
  {id: 'status', name: 'Status', type: 'text'},
  {id: 'item', name: 'Item', type: 'text'},
  {id: 'value', name: 'Value', type: 'number', align: 'right'},
];

const rows = tableRows.map((row, index) => ({
  id: `row_${index + 1}`,
  cells: [
    {value: row.status},
    {value: row.item},
    {value: row.value},
  ],
}));

module.exports = {head, rows};
