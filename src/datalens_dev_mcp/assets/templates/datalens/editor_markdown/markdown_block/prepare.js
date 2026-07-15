/*
 * Editor Markdown template contract:
 * - Source/data contract: sources.js is empty unless Markdown is data-backed.
 * - Params/config: params.json owns optional text variants and links.
 * - Prepare/model normalization: prepare.js returns Markdown payload only.
 * - Render lifecycle: markdown_node renders Markdown natively, no custom HTML wrapper.
 * - Layout/scales: dashboard layout controls placement and size.
 * - Labels/tooltips: section titles are Markdown content only when explicitly requested.
 * - Theme tokens: native Markdown inherits DataLens light/dark theme variables.
 * - Interactions: links must be explicit and safe; selector behavior belongs to relations.
 */
const markdown = '## Methodology\n\nShort source and metric explanation.';

module.exports = {markdown};
