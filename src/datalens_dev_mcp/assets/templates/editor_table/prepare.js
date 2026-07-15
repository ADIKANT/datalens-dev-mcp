/*
 * Editor Table skeleton contract:
 * - Source/data contract: sources.js provides rows with period/value fields.
 * - Params/config: params.js and config.js own table density and pagination.
 * - Prepare/model normalization: prepare.js converts loaded rows into head/rows.
 * - Render lifecycle: table_node renders natively, no custom HTML render.
 * - Layout/scales: dashboard layout and selector relations own table placement.
 * - Labels/tooltips: column labels come from metadata.
 * - Theme tokens: native table styling inherits DataLens theme variables.
 * - Interactions: selector targets are represented outside this file.
 */
const loaded = Editor.getLoadedData();
const rawRows = loaded.rows?.result?.data?.Data || [];
const fields = loaded.rows?.result?.fields || [];
const names = fields.map((field, index) => field.title || field.guid || String(index));
const objects = rawRows.map(row => Object.fromEntries(row.map((value, index) => [names[index], value])));
const columns = ['period', 'value'];
const head = columns.map(name => ({id: name, name, type: 'text'}));
const rows = objects.map(item => ({cells: columns.map(name => ({value: item[name] ?? ''}))}));

module.exports = {head, rows};
