function getPreparedLoadedData(loadedData, sourceName) {
  const sourceData = loadedData[sourceName];
  if (!sourceData) return [];

  const names = sourceData.find(item => item.event === 'metadata')?.data?.names || [];

  return sourceData
    .filter(item => item.event === 'row')
    .map(rowItem => {
      const row = {};
      rowItem.data.forEach((value, idx) => {
        row[names[idx]] = value;
      });
      return row;
    });
}

const options = getPreparedLoadedData(Editor.getLoadedData(), 'environmentOptions')
  .map(row => String(row.environment || '').trim())
  .filter(Boolean)
  .map(value => ({title: value, value: String(value)}));

const content = [{title: 'All environments', value: ''}, ...options];
const currentEnvironment = String(Editor.getParam('environment')?.[0] || '');

// Dynamic selector params are static on the first dashboard render, so repair invalid values here.
if (currentEnvironment && !content.some((option) => option.value === currentEnvironment)) {
  Editor.updateParams({environment: ['']});
}

module.exports = {
  controls: [
    {
      type: 'select',
      param: 'environment',
      label: 'Environment',
      labelPlacement: 'left',
      width: '96%',
      content,
      searchable: false,
      updateOnChange: true
    }
  ]
};
