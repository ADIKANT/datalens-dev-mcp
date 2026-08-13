/**
 * Required edit point: connect your source and preserve the documented output aliases.
 * Route: editor_table. Technical parameter names and aliases are language-neutral.
 */
const {buildSource} = require('libs/dataset/v2');

module.exports = {
  rows: buildSource({
    datasetId: Editor.getId('dataset'),
    columns: ["entity_id", "item", "status", "updated_at", "details_url"],
  }),
};
