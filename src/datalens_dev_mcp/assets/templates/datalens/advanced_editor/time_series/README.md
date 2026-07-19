# Time-series template

Use for `line_chart`, `multiline_chart`, `area_completion`,
`vertical_bar_time_bucket`, `combo_time_series_combo`, and related time variants.
Set optional `series_role` to `comparison` for a faded dashed comparison line;
current and comparison values share one scale. Missing values keep line gaps,
ISO day/month buckets render as `DD.MM.YY`/`MM.YY`, and observed values drive
nice axis ticks. The template keeps direct endpoint labels and safe
`Editor.wrapFn` usage.
