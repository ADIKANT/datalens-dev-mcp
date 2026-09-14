# Maintenance boundaries

- `dl_backup_export` writes exact readbacks plus `manifest.json`. `artifact_kind=snapshot_not_full_restore` and `restore_verified=false` are deliberate until a disposable end-to-end restore is demonstrated.
- `dl_cleanup_preview` follows relations from explicit preserve roots. Apply only an unchanged preview whose ordered delete set is repeated exactly; a missing target is `already_absent`, not a batch-wide failure.
- For standalone HTML Page lifecycle and its distinct iframe contract, use [HTML Pages](html-pages.md). Read active capabilities before claiming a phase is supported.
- Admin inventory is read-only. License assignment is a separate mutation. No revoke capability is claimed.
- Use [authorized scope and delivery](../../datalens-dashboard/references/authorized-scope.md) for authorization, uncertain effects and multi-object completion.

Cleanup identity is the provider entry ID regardless of inventory aliases. Preview retains original preserve roots, reads both relation directions and orders consumers before dependencies. Incomplete or external-consumer scope is a boundary; API-visible relations are not proof of tenant-wide completeness. Apply revalidates the original scope; reconcile `preview_changed` with the authorized set and preserve requirements. Failed or uncertain deletion stops remaining objects and requires reconciliation, not retry or recreation.
