# Source Material Policy

The public repository is an executable toolkit, not a document archive.

Tracked files may contain project-authored code, schemas, configuration,
templates, synthetic examples, tests, and concise operating documentation.
Machine-readable reference data adapted from the official Yandex Cloud
documentation is allowed only with source metadata and the attribution defined
in `THIRD_PARTY_NOTICES.md`.

The repository must not contain:

- credentials, environment files, authentication headers, private keys, or
  production identifiers;
- private dashboard exports, operator logs, internal reports, or local project
  state;
- raw document mirrors, screenshots, page images, copied chapters, or extracted
  source corpora;
- content derived from third-party books, paid courses, or other sources whose
  redistribution terms have not been established.

The official documentation corpus used to regenerate the packaged reference
registries is an external build input. It is never required at runtime. Set
`DATALENS_DOCS_CORPUS_ROOT` explicitly when running the optional compiler.

Every public release must run `python3 scripts/check_public_release.py` against
the tracked tree and built distributions.
