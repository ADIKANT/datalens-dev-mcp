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

## DataLens skills-derived authoring rules

The standalone HTML sandbox, CSP, theme/language, export, and link-integration
rules are distilled from the public
[`datalens-html-pages`](https://github.com/datalens-tech/datalens-skills/tree/8fbb3aabac6b09d4c44f053fa63affea1dc386f7/skills/datalens-html-pages)
skill in `datalens-tech/datalens-skills`.

- Upstream repository: <https://github.com/datalens-tech/datalens-skills>
- Reviewed commit: `8fbb3aabac6b09d4c44f053fa63affea1dc386f7`
- License: Apache License 2.0
- License text: [`LICENSE`](LICENSE)

The raw skill, its template, and its test corpus are not redistributed. The
project contains a compact independent implementation and retains a pinned
source URL and content hash for provenance. No endorsement by the upstream
project is implied.


## Selectively adapted DataLens guidance

Copyright 2026 YANDEX LLC. Licensed under the Apache License, Version 2.0; a copy is supplied in [LICENSE](LICENSE).

The following references were rewritten and selectively adapted for this plugin from `datalens-tech/datalens-skills` commit `603fe462891f99ab6949eec033cb9fcbcf376824`:

- `skills/datalens-inspect/references/installation-and-sdk.md`: installation/object model and installed-version documentation discovery.
- `skills/datalens-inspect/references/cloud-rls-resolution.md`: cloud organization-scoped RLS identity lookup.
- `skills/datalens-maintenance/references/html-pages.md`: standalone HTML Page runtime constraints.

Modifications narrow interface routing and capabilities, preserve typed mutation safeguards, remove automatic environment/auth changes, and retain business-semantic and Browser verification. No upstream executable scripts or templates are included. SDK documentation at tag `v3.0.0`, commit `9114d148ed9ffa2524933988831384184d9db01b`, also informs installed-version documentation discovery under the same copyright/license. Neither selected Apache upstream tree contains a separate NOTICE file.

Exact source paths, commit/tag identities, applicability and deliberate exclusions are recorded in [upstream provenance](skills/datalens-inspect/references/upstream-provenance.md).

The MIT-licensed `datalens-tech/datalens-mcp` README at commit `3638be038284484de8c7320901f745d0c00a0a6f` supplied architectural inspiration for selective schema discovery only; no code, text or bundled dependencies were copied from it.
