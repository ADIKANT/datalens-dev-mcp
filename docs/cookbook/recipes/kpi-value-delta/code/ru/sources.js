/**
 * Обязательная точка изменения: подключите свой источник и сохраните документированные выходные aliases.
 * Route: editor_advanced. Технические имена параметров и aliases оставлены без перевода.
 */
const {buildSource} = require('libs/dataset/v2');

module.exports = {
  rows: buildSource({
    datasetId: Editor.getId('dataset'),
    columns: ["current_value", "comparator_value"],
  }),
};
