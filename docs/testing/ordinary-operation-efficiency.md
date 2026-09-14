# Ordinary operation efficiency

## Recovery guidance and cloud entry names

Receipt presentation derives its next action from item outcomes. Confirmed
rejections direct the caller to correct the specific cause with a new operation
ID for changed input; revision conflicts require a fresh exact target read.
Unknown effects retain reconciliation guidance and request identity. Mixed
batches preserve individual completed, unattempted, rejected and unknown items.
Historical reads normalize their returned view without rewriting stored files
or making another provider attempt. Admission and digest bindings are unchanged.

Cloud entry create and rename validate the verified DataLens US name character
sets before dispatch, including the provider's Unicode spaces. SDK 3.0.0 only
checks a nonempty name and slash handling for path locations. This additional
guard applies to the standard cloud endpoint and supported entry types; custom
endpoints, Enterprise, workbooks and HTML Page remain outside this rule.
Descriptions, field titles, formulas and Editor source are not entry names.
See [contract provenance](../../THIRD_PARTY_NOTICES.md).

This change keeps the direct reader, adapter and durable operation store. It adds no task runtime, cache, evaluator or test file. New pytest cases were not added. Validation below separates local guards from observed installed behavior.

## Addressed check audit

| Real failure | Existing check / observation | Fake boundary | Decision |
| --- | --- | --- | --- |
| Wrong package, missing stdio route, caller cwd polluted | `test_l01_plugin_runtime.py`, manifest portion of `test_l09_public_package.py`, `installed_smoke.py` | Editable/source subprocess cannot establish installed-wheel identity | Consolidate into installed smoke: package/SDK admission, manifest routing, skill discovery, actual stdio, invalid input and empty caller directory. Remove duplicate pytest startup/manifest/word assertions and the duplicate SDK version case |
| Generic writer or task executor accidentally exposed | L09 public-tool names and installed smoke | Structural surface check only | Keep the closed-surface check in installed smoke, without a fixed tool-count assertion |
| Manual Dataset filter or unknown field lost | SDK transport Dataset update, stale/fresh patch and wire checks | Real SDK/handlers, synthetic HTTP and configuration | Keep; extend the existing update scenario with a manual filter and exact no-op, without adding cases |
| Wrong revision/identity/branch attached to old patch | SDK revision and transport guards | Synthetic provider drift | Keep outer revision, inner Dataset revision, identity and branch checks |
| Write replay after timeout, restart or competing process | Interruption, SDK no-replay, mutation admission | Fake network; real receipt files/process locks | Keep intact |
| Full source echoed or credentials retained in receipts | Compact operation and credential-redaction checks | Synthetic content | Keep; verify compact changed paths and explicit detailed retrieval. Compute recorded changes from redacted snapshots so a credential scalar cannot leak through `before`/`after` |
| Invalid nested argument requires guessing | Existing preview argument cases and installed stdio invalid-input request | Rejected before HTTP | Keep; return the exact argument path, expected rule and correction, without all-tool schemas or input values |
| Bounded snapshot loses continuation/drift/unknown dependencies | Existing snapshot continuation cases | Synthetic pages/revisions | Keep intact; no graph traversal added to diff/update |

L09 capability-owner and release-script checks remain structural guards. No passed count is interpreted as live DataLens acceptance.

## Reproduction and measured result

An ephemeral invocation of the existing `test_sdk_v3_transport.py` provider ran the public handler with SDK 3.0.0. The target was a synthetic Dataset containing a manual filter, unknown nested values and an 18,000-character untouched string. The patch changed only `dataset.description`. Both before and after preserve the manual filter and untouched string. No DataLens credentials or objects were used.

| Step | HTTP reads / writes before → after | HTTP response bytes before → after | Text + structured JSON bytes before → after |
| --- | --- | --- | --- |
| Description update | 3 / 1 → 3 / 1 | 74,010 → 74,010 | 425 + 425 → 530 + 530 |
| Same intent, new operation ID | 3 / 1 → 1 / 0 | 74,008 → 18,502 | 421 + 421 → 475 + 475 |
| Diff for the next description | 1 / 0 → 1 / 0 | 18,502 → 18,502 | 18,782 + 18,782 → 242 + 214 |
| Invalid `columns[0]` object | 0 / 0 → 0 / 0 | 0 → 0 | 342 + 342 → 264 + 264 |

These are UTF-8 JSON byte measurements, not model tokens or live latency. HTTP includes the write response; network response size and model output are separate. The compact write result grows slightly to expose changed fields and its readback boundary. Diff drops the unrelated full proposed object by default; `include_proposed=true` restores it in structured data. Full read/snapshot and explicit receipt detail remain in `structuredContent`, with a text summary instead of a second payload copy. Text-only consumers must use structured data for those full results.

A normal update still follows fresh full read → merge → adapter preflight → write → independent saved readback. The existing reader serializes the SDK domain object and does not carry its bound handle to the mutation backend. SDK raw replacement requires that typed target; reconstructing a handle from an old patch or deleting its fetch would remove the current drift check. No shared capture contract was introduced. The second GET remains; a future optimization must bind a fresh handle to exact identity, branch and both Dataset revisions. Preflight is not atomic CAS. SDK returned snapshots may contain input/pre-write fields, so they cannot replace provider readback. Published verification remains separate. HTML Page content guards are unchanged.

## Verification and limits

The affected local run exercised Dataset preservation, one Editor tab/aliases, revision conflicts, exact publication, unknown-outcome reconciliation, multiprocess admission and snapshot continuation. An addressed manual check also verified full-diff opt-in, one-copy read output, alternative argument repairs and JSON boolean-versus-number distinction. The five skill frontmatters validated; their instructions were reviewed by scenario, not tested for required phrases.

The existing native plugin reported package 1.2.0 and SDK 3.0.0 loaded from site-packages. Its auth probe failed during IAM refresh timeout. No authorized run-owned mutation target was provided, so live update/publication, render/business validation and live before/after measurements were not run. Credentials alone would not authorize a canary. No paid replay or host-model evaluation was launched. Candidate distribution smoke and CI results are recorded in the PR; no merge or global installation is part of this change.
