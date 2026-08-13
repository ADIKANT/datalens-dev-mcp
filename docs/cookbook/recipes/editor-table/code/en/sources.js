/**
 * Required edit point: connect your source and preserve the documented output aliases.
 * Route: editor_table. Technical parameter names and aliases are language-neutral.
 */
const {buildSource} = require('libs/dataset/v2');

module.exports = {
  rows: buildSource({
    datasetId: Editor.getId('dataset'),
    columns: ["status", "item", "value"],
  }),
};
