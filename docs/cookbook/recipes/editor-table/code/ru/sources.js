/**
 * Обязательная точка изменения: подключите свой источник и сохраните документированные выходные aliases.
 * Route: editor_table. Технические имена параметров и aliases оставлены без перевода.
 */
const {buildSource} = require('libs/dataset/v2');

module.exports = {
  rows: buildSource({
    datasetId: Editor.getId('dataset'),
    columns: ["status", "item", "value"],
  }),
};
