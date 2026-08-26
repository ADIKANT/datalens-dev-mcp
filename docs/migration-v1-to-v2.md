# Migrating from the legacy tool surface

The autonomous surface is the default. Existing integrations can temporarily select `legacy-v1`, but new clients should move from manual low-level sequences to task ownership:

| Legacy pattern | Autonomous replacement |
|---|---|
| discover, inspect, plan, call save tools manually | `dl_task_start` |
| repeat work after restart | `dl_task_resume` with the same task ID |
| poll raw objects | `dl_task_status` bounded checkpoint |
| request full payloads for proof | `dl_evidence` resource-backed evidence |
| retry failed writes | automatic readback reconciliation |

The new flow does not require a second save or publish confirmation after the user requested the change. Save-only, browser-required, QL, and template migration remain explicit intents. Whole-object deletion, permission changes, credential mutation, and moves remain unsupported or separately guarded.

Before switching a client, run affected, autonomy, and sharded full acceptance, then verify the installed wheel through stdio initialization. Keep the package version unchanged unless a release is separately requested.
