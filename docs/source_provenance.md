# Source Provenance

Public source maps: [Русский](sources.md) · [English](sources_en.md).

## Project-authored surface

The Python implementation, policies, schemas, templates, examples, and tests
are maintained in this repository under Apache License 2.0. Runtime behavior is
defined by those tracked artifacts; it does not read a private document
collection.

## Official Yandex Cloud documentation

The compact registries under
`src/datalens_dev_mcp/assets/schemas/datalens-knowledge/` are adapted from the
official Yandex Cloud documentation:

- source repository: <https://github.com/yandex-cloud/docs>
- DataLens documentation: <https://yandex.cloud/ru/docs/datalens/>
- machine-readable discovery index: <https://yandex.cloud/llms.txt>
- upstream license: Creative Commons Attribution 4.0 International

The documentation was parsed, normalized, indexed, excerpted, and compiled.
Where applicable, registry records retain their source URL, source path,
anchor, and content hash. The packaged registries do not contain the raw site
mirror or its images.

The exact attribution, copyright notice, license copy, snapshot metadata, and
modification statement are recorded in `THIRD_PARTY_NOTICES.md`,
`LICENSES/CC-BY-4.0.txt`, and the adjacent knowledge `PROVENANCE.json`.

## DataLens API contracts

API method names, request shapes, and validation schemas correspond to the
official DataLens API reference stored under `en/datalens/openapi-ref/` and
`md-docs/datalens/openapi-ref/` in the CC-BY-4.0-licensed Yandex Cloud docs
repository. The public OpenAPI response is used only as a deterministic
compiler input and is not distributed. Prose annotations are removed from the
compiled validation bundles; source and modification details are retained in
`schemas/datalens-api/source-trace.json`.

## Regeneration

The full documentation corpus is an external, optional compiler input. Set
`DATALENS_DOCS_CORPUS_ROOT` to an explicitly obtained snapshot before running
the compiler. Production runtime and installed distributions use only the
tracked compact registries.

This project is independent of Yandex and is not endorsed by Yandex.
