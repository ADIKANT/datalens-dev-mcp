/* datalens-protected:renderer:start */
function safeRatio(value, total) {
  return total ? value / total : null;
}

function createRender(rows) {
  return Editor.generateHtml(`<div style="display:grid;font-family:Arial;color:#222;border-radius:8px">${rows.length}</div>`);
}
/* datalens-protected:renderer:end */

const pageSize = /* datalens-slot:pagination:integer:start */50/* datalens-slot:pagination:end */;
const loaded = Editor.getLoadedData();
module.exports = {render: Editor.wrapFn({args: [loaded, pageSize], fn: createRender})};
