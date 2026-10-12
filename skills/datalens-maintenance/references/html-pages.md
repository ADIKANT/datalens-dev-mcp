# Standalone HTML Page boundary

Selectively adapted and capability-gated from upstream DataLens skills. Copyright 2026 YANDEX LLC, Apache-2.0. [Pinned sources and modifications](../../datalens-inspect/references/upstream-provenance.md).

First identify the consumer from current object type and the request. A standalone HTML Page is a report rendered by the platform in a sandboxed iframe. HTML inside an Editor table/chart is governed by [Editor authoring](../../datalens-editor/references/editor-authoring.md), including its supported `Editor.generateHtml` usage. The shared word HTML does not make their runtimes interchangeable.

## Capability before delivery

SDK 3.2 metadata selects object identity and saved/published/exact revision. The read owner obtains an official preview URL for that exact revision and immediately reads bounded UTF-8 HTML with a separate credential-free client. Keep temporary signed URLs out of Git and durable logs. Preview failure leaves content unverified; it does not prove that metadata or a write failed.

Create/update uses the existing typed write owner and semantic content readback. Keep the authored UTF-8 file as an editable artifact. Added CSP is normalized only when absent from authored content. Existing-revision publish needs a fresh `publishedId` matching the selected saved revision and target identity; report content status separately. No generic invoke or browser write fallback is needed.

Use explicit saved/published selection; preview defaults must not choose the branch implicitly. Local artifact, content-checked revision, publication and platform render are distinct evidence. Verify theme/lang and the requested interaction in Browser for visible Page changes.

## Author against## Author against the confirmed Page contract

The pinned upstream Page reference describes an opaque-origin iframe with `sandbox=allow-scripts` and injected CSP. It permits approved static resources while blocking data-network calls. Verify applicability to the target installation before relying on these details:

- Deliver raw UTF-8 HTML with an early charset declaration, no enclosing Markdown fences. Inline only data approved for this artifact. Avoid sensitive viewer data, secrets or runtime parameters in an exported static report.
- Keep interaction state in memory. Fetch/XHR/WebSocket, persistent storage, workers, nested frames, form submissions and ordinary browser downloads are unavailable in this Page contract.
- The upstream allowlist includes jsDelivr, cdnjs, Tailwind CDN and yastatic for scripts; styles also permit Google Fonts CSS. Fonts allow jsDelivr/cdnjs/Google font files and `data:`; images allow yastatic, `data:` and `blob:`; media use `data:` or `blob:`. A different deployment's verified policy takes precedence.
- Read supported `theme` and `lang` query parameters, with sensible defaults. For the confirmed host protocol, exports use `EXPORT` with `data={name,mime,data}`; external links use `OPEN_URL` with `data={url}`. Send host messages only in the framed runtime; preserve ordinary local-preview navigation when no parent handles them.
- Respect the active adapter/provider size limit. The upstream 5–10 MB guidance is not permission to exceed a stricter local limit. Serving URLs can be short-lived; do not treat one as a durable published identity.

Local file preview checks encoding, content and interaction. Platform iframe verification additionally checks actual CSP, resources, theme/language, host export/link behavior and visible output. Lint, local preview and platform render are separate evidence. An unavailable Browser check remains unverified; a blank rendered page is an unresolved defect even when metadata and revision readbacks are correct.
