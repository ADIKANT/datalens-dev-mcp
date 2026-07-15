const regionRows = Editor.getLoadedData('regionOptions') || [];
const countryRows = Editor.getLoadedData('countryOptions') || [];
const currentRegion = String(Editor.getParam('region')?.[0] || 'All');
const currentCountry = String(Editor.getParam('country')?.[0] || 'All');

const regions = ['All'].concat(
  regionRows
    .map((row) => String(row.region || '').trim())
    .filter(Boolean),
);
const availableCountries = ['All'].concat(
  countryRows
    .filter((row) => currentRegion === 'All' || String(row.region || '').trim() === currentRegion)
    .map((row) => String(row.country || '').trim())
    .filter(Boolean),
);

// Dynamic selector params stay static on the first dashboard render, so repair them in controls.js.
if (!regions.includes(currentRegion)) {
  Editor.updateParams({region: ['All'], country: ['All']});
}

if (!availableCountries.includes(currentCountry)) {
  Editor.updateParams({country: ['All']});
}

module.exports = {
  updateControlsOnChange: true,
  controls: [
    {
      type: 'select',
      param: 'region',
      label: 'Region',
      labelPlacement: 'left',
      width: '48%',
      updateOnChange: true,
      content: regions.map((value) => ({title: value, value: String(value)})),
    },
    {
      type: 'select',
      param: 'country',
      label: 'Country',
      labelPlacement: 'left',
      width: '48%',
      updateOnChange: true,
      content: availableCountries.map((value) => ({title: value, value: String(value)})),
    },
  ],
};
