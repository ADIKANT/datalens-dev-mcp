# Official sources and provenance

[Русский](sources.md) · **English** · [Documentation](README_en.md) · [Tools](tools_en.md)

`datalens-dev-mcp` is not a documentation mirror. Runtime behavior comes from project-authored code and policy, while compact reference registries and API schemas are compiled from public primary sources with source metadata retained.

## Three layers of truth

| Layer | What it determines | Where to look |
| --- | --- | --- |
| Official DataLens documentation | Public object model, UI capabilities, Editor, Public API, and authentication requirements | Links below |
| MCP implementation | Which reads, planners, validators, and guarded executors actually exist | [`server.py`](../src/datalens_dev_mcp/server.py), [tool guide](tools_en.md), [API coverage](datalens/api_contract_coverage.md) |
| Local policy | Wizard-first routing, explicit-only QL, save/readback/publish gates, and closed destructive routes | [Route policy](route-policy.md), [Safe Apply](safe-apply.md), [Safety model](local-only-safety-model.md) |

A capability documented by DataLens is not automatically executable through this MCP server. Check a concrete operation with `dl_list_api_methods`, `dl_get_api_method_schema`, `dl_reference(mode="api_contract")`, and the local policy.

## Primary official pages

| Area | Primary source | How the project uses it |
| --- | --- | --- |
| DataLens overview | [DataLens documentation](https://yandex.cloud/ru/docs/datalens/) and [service concepts](https://yandex.cloud/ru/docs/datalens/concepts/) | Terminology, object model, and user-facing capabilities |
| Getting started | [Quickstart](https://yandex.cloud/ru/docs/datalens/quickstart) | Connection → dataset → chart → dashboard relationship |
| Chart technologies | [Chart concept](https://yandex.cloud/ru/docs/datalens/concepts/chart/) | Wizard, QL, and Editor distinction; local policy further constrains route selection |
| Public API | [Working with the Public API](https://yandex.cloud/ru/docs/datalens/operations/api-start) | Base URL, IAM authentication, organization context, and RPC model |
| API methods | [DataLens API Reference](https://yandex.cloud/ru/docs/datalens/openapi-ref/) | Method names, request/response fields, and local API catalog links |
| Workbooks and collections | [Workbooks and collections](https://yandex.cloud/ru/docs/datalens/workbooks-collections/) | Object containers and location semantics |
| Connections | [Connection concept](https://yandex.cloud/ru/docs/datalens/concepts/connection/) | Connection model and sensitive-configuration boundaries |
| Datasets | [Dataset documentation](https://yandex.cloud/ru/docs/datalens/dataset/) | Fields, joins, calculations, and dataset-owned changes |
| Wizard | [Creating a chart](https://yandex.cloud/ru/docs/datalens/operations/chart/create-chart) | Native chart semantics; MCP selects Wizard for standard new charts |
| Editor | [Editor overview](https://yandex.cloud/ru/docs/datalens/charts/editor/) | JavaScript authoring model and runtime boundary |
| Editor tabs | [Editor tabs](https://yandex.cloud/ru/docs/datalens/charts/editor/tabs) | `Meta`, `Params`, `Sources`, `Prepare`, `Config`, `Controls`, and `Activities` |
| Editor methods | [Editor methods](https://yandex.cloud/ru/docs/datalens/charts/editor/methods) | Allowlist and runtime validation for `Editor.*` methods |
| Dashboards | [Dashboard concept](https://yandex.cloud/ru/docs/datalens/concepts/dashboard/) | Tabs, widgets, selectors, links, and layout |
| Access | [DataLens security](https://yandex.cloud/ru/docs/datalens/security/) | Read-only guidance; normal MCP workflow excludes permission mutations |

## Public API contracts

The public OpenAPI response at [`https://api.datalens.tech/json/`](https://api.datalens.tech/json/) is used as a deterministic compiler input. The raw OpenAPI document is not distributed in the package. It is compiled into normalized interoperability contracts with prose annotations removed.

The [tool guide](tools_en.md) maps individual MCP tools to official methods. The full local matrix lives in:

- [`config/datalens_api_methods.json`](../config/datalens_api_methods.json);
- [`config/datalens_api_operation_policy.json`](../config/datalens_api_operation_policy.json);
- [`schemas/datalens-api/source-trace.json`](../schemas/datalens-api/source-trace.json);
- [`docs/datalens/api_contract_coverage.md`](datalens/api_contract_coverage.md).

## Documentation snapshot

The machine-readable [`https://yandex.cloud/llms.txt`](https://yandex.cloud/llms.txt) index was used for page discovery. It is a navigation aid, not a license grant or a standalone redistribution permission.

Current packaged knowledge snapshot:

- generated at: `2026-07-13T13:43:44Z`;
- pages content SHA-256: `fda97edaac019a8f7c74376c7918da5cffb12214cf87de106b7356a59ddccfaf`;
- OpenAPI SHA-256: `e4c3cf56de894e28b883b1f0ceaf2935f68570b052c46885e20bc9608e5ca532`.

Machine-readable sources for these values:

- [`datalens-knowledge/PROVENANCE.json`](../src/datalens_dev_mcp/assets/schemas/datalens-knowledge/PROVENANCE.json);
- [`datalens-api/source-trace.json`](../schemas/datalens-api/source-trace.json).

On regeneration, the documentation checker should compare the published values with these files so the guide cannot drift from packaged assets.

## Licenses and modifications

The official [`yandex-cloud/docs`](https://github.com/yandex-cloud/docs) repository publishes its documentation under [Creative Commons Attribution 4.0 International](https://github.com/yandex-cloud/docs/blob/master/LICENSE). Adapted records were parsed, normalized, indexed, excerpted, summarized, and deduplicated; the repository does not include the full site mirror or its images.

Code, schemas, templates, tests, local policy, and project-authored documentation are licensed under Apache License 2.0. CC BY 4.0 applies only to adapted documentation content. See [`THIRD_PARTY_NOTICES.md`](../THIRD_PARTY_NOTICES.md), [`LICENSES/CC-BY-4.0.txt`](../LICENSES/CC-BY-4.0.txt), and [source provenance](source_provenance.md).

Yandex Cloud, Yandex DataLens, and related marks belong to their respective owners. Their use here is descriptive only and does not imply endorsement.
