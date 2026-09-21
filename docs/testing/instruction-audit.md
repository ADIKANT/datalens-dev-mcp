# Active instruction audit — 1.2.17

Scope: repository instructions, README entrypoints, plugin manifest/MCP registration,
all five skills and their reachable references, public tool schemas, packaged
assets, installation and release guidance. A local path/link/tool-name inventory
preceded addressed reads. Private evidence and scenario identities stay outside
source. This report is not an automatically loaded skill or a mandatory task input.

| File / rule | Established discrepancy | Action / reason retained |
| --- | --- | --- |
| `api/errors.py`, inspect direct reads | 429 suggested correcting the request; normalized delay disappeared from tool/receipt diagnostics | Add `rate_limited`, preserve valid delay, keep one recovery rule in the existing direct-reads reference and link from Inspect/tool docs |
| SDK 3.0.0 HTTP/client contract | Read retry policy includes 429 with backoff that ignores Retry-After; context omits headers but chains HTTPStatusError | Owned response hook surfaces 429 without a new loop; exception conversion also retains allowlisted actual-response metadata |
| `docs/testing/live_test_plan.md` | Removed runtime/auth tools and manifest cleanup action | Replace the existing card with R1–R3, fixed private baseline inputs, real save/publish/UI and exact scoped cleanup |
| `CONTRIBUTING.md` | Removed acceptance script, archive checker called without required archives, obsolete write-enable requirement; dev install omitted test dependencies | Use existing pytest contour, build/archive arguments and authorized typed effects; retain CI requirements |
| `docs/README*.md` | Index said 25 tools while current tools/list exposes 26 | Correct index; retain the closed schema contract |
| `docs/testing/stable-releases.md`, installation link | Intended source was not explicitly fenced by completed Git command and exact merge SHA | State sequential completion/build/install contract; no new installer. Clarify historical SDK 0.9.0 sentence |
| `assets/templates/project/AGENTS.md` | Excluded historical template contains retired mandatory memory read order and routing labels | Mark historical/non-operational; do not ship or impose it on current projects |
| All five skills / known target inventory | Current rules already scope inventory to discovery/completeness | Retain; no blanket inventory after addressed reads |
| Relations and snapshot references | Current `from` dependencies / `to` consumers and continuation are consistent with registry | Retain compatibility default and explicit direction guidance |
| Editor period binding and visual profile | Shared binding, widget title/hint, actual labels, grid defaults and stable colors already have current owners | Retain; no manual Sources generation or unrelated restyling |
| Manifest, schemas and package assets | Valid current tool names/relative references; no all-tool live gate after every edit | Preserve closed schemas and relevant validation; bump synchronized version only |
| Source-pinned examples and historical release evidence | Age alone is not an API contradiction | Preserve provenance/history; add current recovery pointer where relevant |

Validation limitations: existing offline checks are regression evidence, not a live
429 claim. R3 is only observed if ordinary sequential R1/R2 naturally encounters it.
