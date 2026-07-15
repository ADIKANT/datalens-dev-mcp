# Dashboard Canvas

Project-authored dashboard specification template backed by
`config/datalens_dashboard_type_model.json` and native DataLens metadata rules.

## Purpose And Audience

- Purpose:
- Audience:
- Job-to-be-done:
- Success signal:

## Scenarios And Decisions

- Scenario:
- Decision/action:
- Owner:
- Frequency:

## Data Architecture

- Tables:
- Joins:
- Fields:
- Metrics:
- Freshness:
- Data quality caveats:

## Visual Blocks

- Page/tab:
- Chart/control:
- Native dashboard title:
- Native dashboard hint:
- Chart family:
- Route:
- Fallback if evidence is missing:

## Interactions And Success Criteria

- Selectors:
- Relations:
- Success signal:
- Navigation targets:
- Acceptance checklist:

## Conditional UX Acceptance

Record only conditions that apply to this dashboard; do not turn every optional
case into a universal blocker.

- Dense table/export: stable sort, bounded pagination, keyboard/labels, and empty/loading/error/truncated states:
- Mobile/touch: responsive breakpoints, touch targets, and scrolling:
- Status/alert/conflict: noncolor state evidence plus owner/next action:
- Slow/external source: loading, timeout, retry, stale-data, and freshness behavior:
- Last refresh timestamp:
- Owner/support/methodology links:
- Multi-filter reset and visible active/cross-filter state:
- Safe declared navigation targets:
- Readable limitations and errors:

## Native Title/Hint Standard

- Chart title is stored in DataLens dashboard/widget metadata.
- Hint is stored in native metadata and enabled when explanatory context is needed.
- Advanced Editor chart body does not duplicate the title unless explicitly required.
