# Skill contract audit — 1.2.19

Scope: all five skill entrypoints and all eleven shipped Markdown references;
selection boundaries, relative paths/anchors, public tool names and examples,
presentation resolution, mutation/recovery and cleanup rules. The installed
1.2.18 skills matched the reviewed source byte-for-byte before edits. This report
is acceptance documentation, not an additional runtime instruction.

| Skill | Confirmed finding and correction | Retained boundary |
| --- | --- | --- |
| Dashboard | Shared recovery text conflated pre-dispatch failure with confirmed provider rejection; distinguish dispatch state from effect outcome. State presentation precedence once in composition; correct the KPI hint example. | Exact target, compact deltas, preservation, saved/published scope and read-only rendered verification |
| Dataset/Wizard | A blanket sentence about failed-payload replay obscured the shared informed-repeat exception; route unknown effects to that owner. | GUID/type/grain checks, source readiness, native technology and separate validation/data/render evidence |
| Editor | Reference claimed reference styling outranked user/project choices, contrary to the resolver. Correct default hint ownership, make defaults inspection conditional because compile resolves it, and label dates as an example. | Existing-tab preservation, subtype-specific validation, shared live Dataset binding and no manual renderer regeneration |
| Inspect | Inventory wording could imply a full workbook listing for exact-candidate cleanup or exact-target absence. Narrow it to inventory-wide claims/discovery. | Direct reads, honest pagination, same-account authentication, rate-limit budget and unresolved identity handling |
| Maintenance | Unconditional backup/cleanup inventory caused extra workbook scans for known targets. Separate set discovery from exact backup and dependency preview. | Fresh complete preview, preserve roots, exact ordered delete set, stop on uncertain effects; Page content writes remain unsupported |

Validation uses the actual profile resolver, shipped JSON examples, public schemas,
existing focused checks and final offline acceptance. No new test files, HTTP
substitutes, provider writes, directory dumps or paid evaluation series were added.
All 38 current local Markdown links/anchors resolve (36 before the corrections); every referenced `dl_*` name exists.
All four JSON examples pass their relevant local validator/schema (the selector
fragment is embedded in a complete typed dashboard draft). These are static
contract checks, not a claim of live provider or rendered acceptance.

Primary-source checks retained the existing restrictions for
[Measure Names/Values](https://yandex.cloud/en/docs/datalens/concepts/chart/measure-values)
and [LOD with time-series functions](https://yandex.cloud/ru/docs/datalens/concepts/lod-aggregation).
The [pinned RLS subject map](https://github.com/datalens-tech/datalens-skills/blob/603fe462891f99ab6949eec033cb9fcbcf376824/skills/datalens-yc-rls-resolve/references/id-formats.md)
and [Page iframe constraints](https://github.com/datalens-tech/datalens-skills/blob/603fe462891f99ab6949eec033cb9fcbcf376824/skills/datalens-html-pages/references/authoring-constraints.md)
remain version/installation scoped. Current adapter support was checked separately;
reference existence does not authorize or prove a live capability.

No contradiction was found in routing Wizard versus Editor versus Page, RLS read
scope, authentication recovery, current relations direction, rate-limit recovery,
or save/publish/restore preservation. This does not claim every provider/runtime
branch was executed. Prior unknown writes and incomplete visual acceptance remain
separate pending evidence; a skill audit cannot settle them.

# Previous bounded audit — 1.2.17

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
