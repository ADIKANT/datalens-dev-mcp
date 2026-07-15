/*
 * Advanced Editor skeleton contract:
 * - Source/data contract: sources.js provides period/value rows.
 * - Params/config: params.js controls filters and theme, not hardcoded JS branches.
 * - Prepare/model normalization: prepare.js builds a serializable model before render.
 * - Render lifecycle: render is exported as Editor.wrapFn and returns Editor.generateHtml.
 * - Layout/scales: compact KPI body leaves title/hint to native dashboard metadata.
 * - Labels/tooltips: body labels explain values only.
 * - Theme tokens: CSS uses DataLens/Gravity variables for light and dark themes.
 * - Interactions: selector bindings stay in dashboard relations.
 */
const model = {status: 'Ready'};
module.exports = {
  render: Editor.wrapFn({
    args: [model],
    fn: function(options, data) {
      const text = String(data.status || 'Ready').replace(/</g, '&lt;').replace(/>/g, '&gt;');
      return Editor.generateHtml(
        `<div style="font-family:Arial,sans-serif;padding:12px;color:var(--g-color-text-primary,inherit);background:var(--g-color-base-background,transparent)"><div>${text}</div></div>`,
      );
    },
  }),
};
