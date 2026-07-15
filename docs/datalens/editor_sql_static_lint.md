# Editor SQL Static Lint

Editor SQL static lint catches generated Source/Editor SQL patterns that have
failed in live ClickHouse/DataLens runs. It is a preflight gate, not runtime SQL
execution.

Rules with `error` severity:

- `tuple_indexing`: flags tuple-like access such as `diagnostic_item[1]` and
  suggests `tupleElement(diagnostic_item, 1)`.
- `arrayzip_independent_regex_lists`: flags `arrayZip` over multiple
  independent `extractAll(...)` arrays. Parse one object or fragment per row
  before extracting fields.
- `unsafe_single_quote_regex_escape`: flags `\\'` style regex escaping and
  suggests `\\x27`.
- `no_common_type_prone_ifnull`: flags `ifNull(entity_id, '')` and similar
  nullable/id/state defaults where `toString(...)` should be applied first.
- `no_common_type_prone_join`: flags id joins without explicit casts when
  source fields can be mixed Int/String; matching supplied field-type evidence
  suppresses the warning.
- `raw_payload_default_visible`: flags raw JSON payload fields such as
  `event_payload_json` unless they are explicitly limited to diagnostics.
- `availability_default_regression`: flags availability fields that default to
  `0` when local rules say DEV/test runtime availability should remain true.
- `correlated_subquery_unsupported`: flags correlated subquery shapes that can
  fail in ClickHouse with unsupported-method errors.
- `unknown_alias_reference`: flags references to aliases that are not visible in
  the current SQL text.
- `aggregate_alias_shadows_input`: flags shapes such as `sum(value) AS value`
  that ClickHouse can expand into illegal nested aggregation.
- `aggregate_alias_reaggregated`: flags reuse inside the same SELECT list.
  Rolling up a materialized CTE aggregate and legal scalar formatting such as
  `round(sum(value), 2)` are not rejected.
- `or_join_memory_explosion`: flags joins whose `ON` clause contains `OR`.
- `pairwise_join_memory_explosion`: flags `CROSS JOIN` and `JOIN ... ON 1=1`.
- `missing_early_filter` / `late_filter_after_wide_scan`: enforce configured
  task/request filters before wide history joins.
- `select_star_prod_probe`: rejects `SELECT *` for production probe contexts.
- `rollup_final_join_shape`: flags final `SELECT` from a rollup CTE that
  reintroduces joins after aggregation.
- `unsafe_internal_name`: reuses the DataLens technical-name sanitizer for
  serialized payloads.

The lint result is structured:

```json
{
  "ok": false,
  "checked_paths": ["dashboard/source_tables/sources.js"],
  "issues": [
    {
      "severity": "error",
      "rule": "tuple_indexing",
      "path": "dashboard/source_tables/sources.js",
      "message": "diagnostic_item[1] is tuple-like indexing",
      "suggested_fix": "Use tupleElement(diagnostic_item, 1)"
    }
  ]
}
```

Use it before live save/publish through `dl_validate_project` or project live
workflow summaries. If direct SQL execution is unavailable, combine this lint
with generated-query inspection, save/publish acceptance, object readback, and
manual UI smoke.

Static lint is evidence level `STATIC_SQL_LINT`. It is not runtime execution.
Use recorded read-only provider output with `dl_diagnose` for
`ENGINE_SCHEMA_PROBE` or `ENGINE_STAGE_PROBE` evidence.
