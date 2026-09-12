# Standalone HTML Page boundary

Selectively adapted and capability-gated from upstream DataLens skills. Copyright 2026 YANDEX LLC, Apache-2.0. [Pinned sources and modifications](../../datalens-inspect/references/upstream-provenance.md).

First identify the consumer from current object type and the request. A standalone HTML Page is a report rendered by the platform in a sandboxed iframe. HTML inside an Editor table/chart is governed by [Editor authoring](../../datalens-editor/references/editor-authoring.md), including its supported `Editor.generateHtml` usage. The shared word HTML does not make their runtimes interchangeable.

## Capability before delivery

Check the active typed tool schema and the configured installation's supported Page contract. A reference, an SDK symbol or a local successful HTML lint does not prove an upload or publish route. Use only the verified existing mutation service; do not invent a Page endpoint, presigned upload, generic invoke, or browser write fallback. If the required provider operation is unsupported, finish any authorized local artifact work and state precisely that upload/publication remains unsupported. Keep save/readback, publish (where that type supports a separate phase), and rendered verification distinct.

## Author against the confirmed Page contract

The pinned upstream Page reference describes an opaque-origin iframe with `sandbox=allow-scripts` and injected CSP. It permits approved static resources while blocking data-network calls. Verify applicability to the target installation before relying on these details:

- Deliver raw UTF-8 HTML with an early charset declaration, no enclosing Markdown fences. Inline only data approved for this artifact. Avoid sensitive viewer data, secrets or runtime parameters in an exported static report.
- Keep interaction state in memory. Fetch/XHR/WebSocket, persistent storage, workers, nested frames, form submissions and ordinary browser downloads are unavailable in this Page contract.
- The upstream allowlist includes jsDelivr, cdnjs, Tailwind CDN and yastatic for scripts; styles also permit Google Fonts CSS. Fonts allow jsDelivr/cdnjs/Google font files and `data:`; images allow yastatic, `data:` and `blob:`; media use `data:` or `blob:`. A different deployment's verified policy takes precedence.
- Read supported `theme` and `lang` query parameters, with sensible defaults. For the confirmed host protocol, exports use `EXPORT` with `data={name,mime,data}`; external links use `OPEN_URL` with `data={url}`. Send host messages only in the framed runtime; preserve ordinary local-preview navigation when no parent handles them.
- Respect the active adapter/provider size limit. The upstream 5–10 MB guidance is not permission to exceed a stricter local limit. Serving URLs can be short-lived; do not treat one as a durable published identity.

Local file preview checks encoding, content and interaction. Platform iframe verification additionally checks actual CSP, resources, theme/language, host export/link behavior and visible output. Lint, local preview and platform render are separate evidence. An unavailable Browser check remains unverified; a blank rendered page is an unresolved defect even after successful save/readback.
