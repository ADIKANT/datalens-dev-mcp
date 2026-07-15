## Summary

Describe the problem and the smallest change that solves it.

## Validation

List the exact commands and results.

```text
python scripts/run_offline_acceptance.py
```

## Safety and provenance checklist

- [ ] Tests cover changed behavior.
- [ ] User-visible changes are documented.
- [ ] Route-policy changes include matching config, schema, validator, example, documentation, and test updates.
- [ ] The change preserves read-only defaults and guarded-write semantics.
- [ ] Fixtures and examples are synthetic.
- [ ] The diff contains no credentials, private IDs, customer data, raw exports, absolute home paths, books, courses, copied chapters, or full documentation mirrors.
- [ ] Any permitted third-party adaptation includes source, copyright, license, attribution, and modification details.
