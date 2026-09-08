# Visualization decisions

Read the relevant section for a new visual or semantic change. A rename or spacing fix does not require a new data inventory, external Canvas, or approval. Infer audience, question/action, metric, slice and comparison from available context. Preserve an explicit accepted reference and manual composition.

## Question, metric and comparison

Use a table for exact lookup; a time series for trends; ranked bar/dot for category magnitude; part-to-whole only for a valid whole; bins/quantiles for distributions; scatter for association without a causal claim. Prefer native Wizard for new standard charts while preserving an existing technology. Bullet/target bars, small multiples and distribution views are options when needed, not a mandate to implement new families.

Distinguish measures, identifiers and categories: versions and vehicle identifiers are not numeric measures. Establish definition, unit, grain, aggregation, comparison base and missingness from requirements, metadata and actual data. Do not sum percentages/distinct counts or average averages. Source-computed non-additive totals remain authoritative. Never invent a target, threshold, owner or benchmark.

KPI arithmetic sign and favorable direction differ: lower latency can be better. Preserve declared `higher_is_better`, `lower_is_better`, or `neutral`; unknown direction is neutral. Recipe presentation uses `kpi.direction`, `kpi.delta_kind` (`relative`, `absolute`, `percentage_points`), and `kpi.value_scale` (`null`, `fraction`, `percent`). The same keys on `metric` seed values; selected profiles/references and explicit presentation overrides take precedence. Select the delta kind and scale: 80% to 84% (or 0.8 to 0.84) is +4 percentage points or +5% relative. The supported relative calculation uses `(current - previous) / abs(previous)`; a zero base is undefined, never Infinity. Missing values remain missing, and formatting preserves raw point precision. Body and tooltip agree on units, dates and precision. Compare incomplete periods on a comparable basis or explain the difference. Intentional cumulative-lag windows may overlap.

## Time and scales

Calendar distances represent elapsed time or explicitly aligned periods. In recipe bindings, `date.mode` is `auto`, `calendar`, `temporal`, or `ordinal`, with optional `granularity` of `day`, `week`, or `month`. Known grids use UTC boundaries and month starts; grid filling does not recompute KPI totals. Irregular ISO dates are spaced proportionally; explicit ordinal comparisons remain aligned. When granularity is known, prepare a complete calendar with null for missing periods. Missing is not zero; do not connect missing observations or interpolate without a specified method. Arbitrary categories remain ordinal.

Bars and filled areas encode magnitude from a visible baseline; preserve signed values. Positive and negative stacks need separate accumulation. Lines may have a nonzero minimum when the range is clear. Compare panels on comparable scales; label units and series-to-axis mapping for dual axes and never tune scales to imply correlation. Simple panels can help, but accepted dual-axis compositions need no unsolicited redesign. Verify supported signed geometry in the consumed renderer before publication.

## Text, color and page role

Object name, visible title, hint, annotation and tooltip have separate owners. Show the title once. Use stable descriptive/question titles for filterable dashboards; a static explanatory conclusion must be supported by data. Shared period/filter context belongs in the page header; expose local exceptions. Hints explain calculation and limits, tooltips explain the hovered element, units, dates, comparison and missing status. Essential meaning and values must remain available without hover.

Use categorical color for versions/status, sequential/diverging color for scales, and goal-dependent evaluation for KPI. Preserve current/previous/target meanings, legends, text labels and accepted palettes. An overview answers a few key questions; a management/detail page can be long or tabbed with shared filters. Do not squeeze a wide management table into one screen or add unrelated blocks.

## Applicable project examples and accepted families

The existing 62 use-case IDs remain the capability catalogue; this reference neither replaces nor reduces them. These 12 generic project examples retain applicability without shipping private project names, IDs, data or layouts:

1. Order intake: responsive KPI badge, inline hint, previous-value block and filled sparkline; weekly grouped table with ISO weeks, numeric alignment, fixed widths, pinned groups/totals, bottom total and manual height.
2. Vehicle utilization: comparable fleet/time slices and explicit utilization definitions.
3. Fleet service: management detail, stable vehicle identifiers and source freshness.
4. Pipeline checks: execution status, missing/error distinction and drilldown.
5. Platform change reporting: change/version context and comparable reporting periods.
6. ETL orchestration: dependency-aware execution overview and detail.
7. Notifications: delivery/failure measures with explicit denominators.
8. Launch readiness: milestone/status context without invented targets.
9. Telematics: time coverage, irregular observations and gaps.
10. Vehicle inventory: identifiers, exact counts and relevant inventory grain.
11. Version compatibility: parent-aware multilevel headers; hardware/software/bootloader distinctions; pinned header/key column; manual, not-applicable and missing states; scrolling. Never collapse version strings into current/previous/delta or good/bad.
12. Service period comparison: preserve accepted current/comparison series, hover, markers, labels, gridlines and legend while retaining honest signed scales.

Select the corresponding real project reference when available; these examples are not runtime dependencies or replacement compositions. Verify query/results, dates/units, renderer/widget property consumption and filter behavior separately from API saved/published identity. Configuration presence and test counts do not prove the visual result.
