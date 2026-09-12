# HTML in DataLens

[Русский](html_pages.md)

Choose by the actual consumer: HTML inside an Editor table/chart follows the [Editor runtime](../../skills/datalens-editor/references/editor-authoring.md), while a standalone Page follows the [Page capability and iframe contract](../../skills/datalens-maintenance/references/html-pages.md). They are different object types and execution environments.

The current interface uses typed object operations. The historical `dl_generate_editor_bundle` / `dl_validate_editor_runtime_contract` HTML generator workflow is not an available tool route. Prepare an authorized local UTF-8 artifact when needed; use current tool schemas and the existing guarded lifecycle for supported provider operations. A reference does not establish active installation support or supply a missing upload endpoint.

The SDK v3.0.0 specs contain Page create/get/update/delete, but `GetHtmlPageResult` returns metadata and `meta.objectId` without HTML content. The adapter rejects Page creation and content updates before dispatch until content readback can be verified. Finish the authorized local artifact and report that precise unsupported step.

Metadata reads and validated publication of an existing exact saved revision remain separate supported operations. Publication uses the update method's revision/mode contract, not a separate endpoint; it does not prove this adapter authored or read that revision's content. Preserve exact target/revision checks, receipt reconciliation and saved/published identity readback.

Report local artifact/lint, saved state, published state and platform iframe render separately. Local Browser preview does not reproduce the platform CSP or host export behavior. Correct metadata or revision readback does not verify HTML content or fix a blank rendered Page.
