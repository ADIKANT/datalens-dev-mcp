# Maintenance boundaries

- `dl_backup_export` writes exact readbacks plus `manifest.json`. `artifact_kind=snapshot_not_full_restore` and `restore_verified=false` are deliberate until a disposable end-to-end restore is demonstrated.
- `confirmed_delete` must match the authorized exact scope and fresh preview; it is not an additional human-confirmation token.
- `dl_cleanup_preview` follows relations from explicit preserve roots. Apply only an unchanged preview whose ordered delete set is repeated exactly; a missing target is `already_absent`, not a batch-wide failure.
- For standalone HTML Page lifecycle and its distinct iframe contract, use [HTML Pages](html-pages.md). Read active capabilities before claiming a phase is supported.
- Admin inventory is read-only. License assignment is a separate mutation. No revoke capability is claimed.
- For a multi-object cleanup, preserve an exact row per object with intended effect, preview/readback evidence, and remaining state. Completion of one deletion does not prove completion of the requested set. Keep an old cleanup plan as historical context until the current request authorizes that exact destructive scope and a fresh preview still matches it.

Cleanup identity is the provider entry ID regardless of inventory aliases. Preview retains original preserve roots, reads both relation directions and orders consumers before dependencies. Incomplete or external-consumer scope is a boundary; API-visible relations are not proof of tenant-wide completeness. Apply revalidates the original scope; reconcile `preview_changed` with the authorized set and preserve requirements. Failed or uncertain deletion stops remaining objects and requires reconciliation, not retry or recreation.
