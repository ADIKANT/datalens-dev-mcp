# Local live verification

Use [current testing instructions](testing.md) and the [public autonomy scenarios](public-autonomy-canary.md). Test only explicitly authorized, run-owned objects in the selected project. Keep API/data/render evidence separate; fixture tests do not prove live behavior.

Cleanup uses `dl_cleanup_preview` and exact `confirmed_delete`, preserves dependencies, and reads back the result. Unknown effects require read-only reconciliation before any repeat. Restore only temporary selector values changed by the check, using their observed initial values.
