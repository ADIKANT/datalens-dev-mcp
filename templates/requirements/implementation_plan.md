# Implementation Plan

Source of truth: `requirements/*.md`.

## Current Known Context

- Missing.

## Dashboard Blueprint

- Type:
- Reason:
- Job-to-be-done:
- Layout:
- Selector/filter behavior:
- Navigation/relations:

### Draft Chart Plan

- Family:
- Route:
- Required parameters:
- Fallback:

### Deterministic Change Budget

- Planned creates:
- Planned updates:
- Expected active objects after readback:
- Owned payload paths:
- Preserved geometry/object ids:
- Semantic no-op fingerprint:

### Runtime And Responsive Acceptance

- Browser capture contract: `datalens.browser_capture.v2`.
- Change scope: `content`, `layout`, or `dashboard`.
- Compact and wide desktop viewport evidence for layout/dashboard changes.
- Changed tabs checked from top through bottom; internal table scrolling checked.
- No horizontal overflow, clipping, missing changed objects, duplicate labels, or console/runtime errors.
- Period/Comparison selectors and required hints exercised in the rendered dashboard.

### Critical Questions

- Missing requirements produce targeted questions here.

## Drift Prevention

- Chart/dashboard generation must read this requirements workspace before implementation.
- User corrections go to `user_decisions.md` and `change_log.md`.
- Missing requirements must produce a targeted question, not an invented assumption.
- Repeated apply with an unchanged semantic fingerprint must produce zero geometry drift.
