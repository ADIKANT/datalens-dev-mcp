# Third-party notices

The project source code, project-authored documentation, configuration,
schemas, templates, and tests are licensed under the Apache License 2.0 unless
a file or the notice below says otherwise.

## Yandex Cloud documentation-derived reference data

Some packaged reference records are adapted from the public Yandex Cloud
documentation, including Yandex DataLens documentation.

- Copyright: (C) YANDEX LLC, 2018
- Upstream source repository: <https://github.com/yandex-cloud/docs>
- Published documentation: <https://yandex.cloud/ru/docs/datalens/>
- License: Creative Commons Attribution 4.0 International (CC BY 4.0)
- License text: [`LICENSES/CC-BY-4.0.txt`](LICENSES/CC-BY-4.0.txt)
- License URL: <https://creativecommons.org/licenses/by/4.0/>

The upstream `llms.txt` index at <https://yandex.cloud/llms.txt> was used as a
discovery aid. It is not treated as a license grant.

The documentation-derived records were parsed, normalized, indexed,
excerpted, summarized, deduplicated, and compiled into machine-readable
registries for local retrieval. The distributed project does not contain a
full mirror of the upstream documentation or its image assets. Source URLs,
document paths, and content hashes are retained in the generated records where
available so that attribution and provenance can be traced.

Snapshot-level provenance and the list of covered registries are recorded in
`src/datalens_dev_mcp/assets/schemas/datalens-knowledge/PROVENANCE.json`.

The generated registries under
`src/datalens_dev_mcp/assets/schemas/datalens-knowledge/` can contain a mixture
of documentation-derived records, project-authored policy metadata, and public
API interface facts. CC BY 4.0 applies only to material adapted from the
Yandex Cloud documentation. It does not relicense project-authored material or
the API interface facts described below.

No endorsement by Yandex LLC is implied.

## DataLens public API reference-derived contracts

Selected method names, endpoint paths, request and response property names,
and normalized schema fragments correspond to the public DataLens API
reference maintained in the CC-BY-4.0-licensed Yandex Cloud documentation
repository under `en/datalens/openapi-ref/` and
`md-docs/datalens/openapi-ref/`. The public OpenAPI endpoint at
<https://api.datalens.tech/json/> was used as a deterministic compiler input.

The raw OpenAPI document is not included in this distribution. Upstream prose
annotations such as schema titles, descriptions, summaries, and examples are
removed; the remaining artifacts contain normalized interoperability
contracts used for validation. Source, license, modification, and
transformation metadata are recorded in
`schemas/datalens-api/source-trace.json` and its packaged mirror. CC BY 4.0
applies to adapted API-reference documentation; project-authored support and
write-safety policy remains Apache-2.0.

Yandex Cloud, Yandex DataLens, and related marks belong to their respective
owners. Their use here is solely descriptive.
