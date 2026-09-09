# Maintenance boundaries

- `dl_backup_export` writes exact readbacks plus `manifest.json`. `artifact_kind=snapshot_not_full_restore` and `restore_verified=false` are deliberate until a disposable end-to-end restore is demonstrated.
- `confirmed_delete` must match the authorized exact scope and fresh preview; it is not an additional human-confirmation token.
- `dl_cleanup_preview` follows relations from explicit preserve roots. Apply only an unchanged preview whose ordered delete set is repeated exactly; a missing target is `already_absent`, not a batch-wide failure.
- HTML Page content is one UTF-8 string, limited to 5 MiB by this adapter. Create/update/publish use the documented Public API adapter and never a browser fallback.
- Admin inventory is read-only. License assignment is a separate mutation. No revoke capability is claimed.
- For a multi-object cleanup, preserve an exact row per object with intended effect, preview/readback evidence, and remaining state. Completion of one deletion does not prove completion of the requested set. Keep an old cleanup plan as historical context until the current request authorizes that exact destructive scope and a fresh preview still matches it.
