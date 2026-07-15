# Resource schedule exception

Explicit-only Advanced Editor recipe for resource-by-time conflict analysis. It is
not a generic timeline family and must never be selected as an alias or fallback.

Required source aliases are `resource_id`, `resource_name`, `item_id`, `start_at`,
`end_at`, and `status`. Timestamps must be ISO-8601 values with `Z` or an explicit
numeric offset. `timezone` and `as_of` are injected parameters; the renderer never
uses the browser clock.

The template assigns lanes deterministically after sorting by resource, start,
end, and item id. Intervals overlap only when `next.start < current.end`; adjacent
intervals do not conflict. Ignored statuses are excluded from conflict marking.
Conflict and anomaly states are rendered with text as well as color.

The Advanced renderer fails closed to a `table_node` fallback model if timestamps
are invalid or if row, resource, lane, span, or serialized-model caps are exceeded.
Defaults are 1,000 rows, 50 resources, 8 lanes per resource, a 90-day span, and
120,000 UTF-8 model bytes. `timezone` must be an IANA identifier such as
`Etc/UTC`; local browser time is never consulted.
Links use the shared URI policy: HTTPS and relative links are allowed, HTTP is an
explicit opt-in, and rejected links remain plain text.
