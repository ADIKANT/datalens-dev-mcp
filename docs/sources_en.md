# Official sources

[Русский](sources.md) · **English** · [Project home](../README_en.md)

[Quick start](../README_en.md#quick-start) · [DataLens access](access_en.md) · [Connect](codex_setup_en.md) · [Tools](tools_en.md) · [Workflows](usage-flow_en.md) · **Sources** · [Safety](local-only-safety-model_en.md) · [Русский](sources.md)

The server is based on official DataLens documentation, the public OpenAPI contract, and safe execution rules implemented in this repository.

## Source map

| Area | Official page | Project use |
| --- | --- | --- |
| DataLens | [DataLens documentation](https://yandex.cloud/ru/docs/datalens/) | Terminology, object model, and user capabilities |
| Charts | [Wizard, QL, and Editor](https://yandex.cloud/ru/docs/datalens/concepts/chart/) | Technology and visualization selection |
| Public API | [API getting started](https://yandex.cloud/ru/docs/datalens/operations/api-start) | API URL, IAM token, organization ID, and request example |
| API methods | [DataLens API Reference](https://yandex.cloud/ru/docs/datalens/openapi-ref/) | Method names and request/response fields |
| Editor | [Editor tabs](https://yandex.cloud/ru/docs/datalens/charts/editor/tabs) | JavaScript Editor object structure |
| Editor runtime | [Editor methods](https://yandex.cloud/ru/docs/datalens/charts/editor/methods) | Validation of allowed `Editor.*` calls |
| Standalone HTML | [`datalens-html-pages`](https://github.com/datalens-tech/datalens-skills/tree/main/skills/datalens-html-pages) | Sandbox/CSP, theme/lang, and parent-message protocols; not a Public API upload source |
| Dashboards | [Dashboard model](https://yandex.cloud/ru/docs/datalens/concepts/dashboard/) | Tabs, widgets, selectors, relations, and layout |
| Workbooks | [Workbooks and collections](https://yandex.cloud/ru/docs/datalens/workbooks-collections/) | Object location and access control |
| Datasets | [Dataset documentation](https://yandex.cloud/ru/docs/datalens/dataset/) | Fields, relations, calculations, and data model |
| Connections | [Connections](https://yandex.cloud/ru/docs/datalens/concepts/connection/) | Connection types and confidential-setting boundaries |
| Access | [DataLens roles](https://yandex.cloud/ru/docs/datalens/security/roles) | Permissions for reading, editing, and publishing |
| Documentation license | [CC BY 4.0 in yandex-cloud/docs](https://github.com/yandex-cloud/docs/blob/master/LICENSE) | Attribution for adapted reference data |

## Three functional layers

| Layer | Scope | Reference |
| --- | --- | --- |
| DataLens capabilities | Objects, UI, Editor, and Public API methods | Official pages above |
| MCP implementation | The 38 available tools, inputs, and results | [Tool guide](tools_en.md), [technical catalog](mcp/tools.md), [API coverage](datalens/api_contract_coverage.md) |
| Execution rules | Chart technology, revision checks, save, publish, and deletion | [Route policy](route-policy_en.md), [Safe Apply](safe-apply_en.md), [safety model](local-only-safety-model_en.md) |

Before execution, the server checks the operation against its current method catalog and execution rules. Use `dl_list_api_methods` and `dl_get_api_method_schema` to inspect a particular method.

## Public API contracts

The public OpenAPI schema at [`https://api.datalens.tech/json/`](https://api.datalens.tech/json/) is a compiler input. It produces compact validation contracts and the method catalog:

- [`config/datalens_api_methods.json`](../config/datalens_api_methods.json);
- [`config/datalens_api_operation_policy.json`](../config/datalens_api_operation_policy.json);
- [`schemas/datalens-api/source-trace.json`](../schemas/datalens-api/source-trace.json);
- [`docs/datalens/api_contract_coverage.md`](datalens/api_contract_coverage.md).

The package contains compiled contracts. `source-trace.json` stores machine-readable data used to verify provenance and reproducible generation.

## Documentation-derived reference data

The official `llms.txt` index was used to discover documentation pages. Yandex Cloud documentation is distributed under CC BY 4.0. Links: [llms.txt](https://yandex.cloud/llms.txt), [yandex-cloud/docs license](https://github.com/yandex-cloud/docs/blob/master/LICENSE).

Pages were parsed, normalized, distilled into applicable rules, and linked to their originals. The package contains compact indexes and schemas.

Machine-readable generation data is stored in:

- [`datalens-knowledge/PROVENANCE.json`](../src/datalens_dev_mcp/assets/schemas/datalens-knowledge/PROVENANCE.json);
- [`datalens-api/source-trace.json`](../schemas/datalens-api/source-trace.json).

`dl_reference` uses these local records. Normal runtime does not download the documentation corpus.

The public `datalens-tech/datalens-skills` repository is used only as a compact
standalone-HTML authoring contract. Its raw skill, template, and eval corpus are
not packaged. The reviewed source commit and hash are retained in the recipe
and runtime result.

## Licenses and attribution

Project code, schemas, templates, tests, and original documentation are licensed under the [Apache License 2.0](../LICENSE). Content adapted from Yandex Cloud documentation includes [CC BY 4.0](../LICENSES/CC-BY-4.0.txt) attribution and a modification notice.

See [`THIRD_PARTY_NOTICES.md`](../THIRD_PARTY_NOTICES.md) for complete notices and [`source_provenance.md`](source_provenance.md) for the technical provenance description.

Yandex Cloud, Yandex DataLens, and related trademarks belong to their respective owners.
