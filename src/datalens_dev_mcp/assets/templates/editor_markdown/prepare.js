/*
 * Editor Markdown skeleton contract:
 * - Source/data contract: sources.js is empty unless Markdown is data-backed.
 * - Params/config: params.js owns optional content variants.
 * - Prepare/model normalization: prepare.js returns Markdown only.
 * - Render lifecycle: markdown_node renders natively, no custom HTML render.
 * - Layout/scales: dashboard layout controls placement.
 * - Labels/tooltips: dashboard title and hint stay in native metadata.
 * - Theme tokens: native Markdown inherits DataLens theme variables.
 * - Interactions: links must be explicit and safe.
 */
const markdown = '## Synthetic methodology\n\nThis local example contains no sensitive IDs or customer data.';

module.exports = {markdown};
