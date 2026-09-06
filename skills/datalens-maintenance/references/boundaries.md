# Maintenance boundaries

- `dl_backup_export` writes exact readbacks plus `manifest.json`. `artifact_kind=snapshot_not_full_restore` and `restore_verified=false` are deliberate until a disposable end-to-end restore is demonstrated.
- `dl_cleanup_preview` follows relations from explicit preserve roots. Apply only an unchanged preview whose ordered delete set is repeated exactly; a missing target is `already_absent`, not a batch-wide failure.
- HTML Page content is one UTF-8 string, limited to 5 MiB by this adapter. Create/update/publish use the documented Public API adapter and never a browser fallback.
- Admin inventory is read-only. License assignment is a separate mutation. No revoke capability is claimed.
