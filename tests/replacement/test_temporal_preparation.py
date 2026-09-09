import json
import subprocess

from datalens_dev_mcp.authoring.recipes import compile_recipe


def prepare(recipe, data, date=None, comparison=None, source=False):
    bindings = {'metric': {}, 'date': date or {}, 'comparison': comparison or {}}
    if source:
        bindings['source'] = {'meta': {}, 'sources_js': 'module.exports={};',
                              'prepare_js': 'module.exports=' + json.dumps(data) + ';'}
    else:
        bindings['prepared_data'] = data
    draft = compile_recipe(recipe, bindings, user_config_path='/nonexistent/profile.json')['draft']
    script = 'global.Editor={wrapFn:x=>x,generateHtml:x=>x};\n' + draft['tabs']['prepare.js']
    script += '\nconsole.log(JSON.stringify(module.exports.render.args[0]));'
    return json.loads(subprocess.check_output(['node', '-e', script], text=True))


def test_daily_kpi_source_and_prepared_fill_null_without_changing_summary():
    data = {'value': 13, 'previous': 10, 'points': [
        {'date': '2026-09-01', 'value': 1}, {'date': '2026-09-02', 'value': 2},
        {'date': '2026-09-10', 'value': 10}]}
    for source in (False, True):
        actual = prepare('kpi_sparkline', data, {'granularity': 'day'}, source=source)
        assert len(actual['points']) == 10
        assert [p['value'] for p in actual['points']] == [1, 2] + [None] * 7 + [10]
        assert actual['value'] == 13 and actual['previous'] == 10


def test_daily_series_aligns_missing_and_comparison_without_interpolation():
    data = {'categories': ['2026-09-01', '2026-09-02', '2026-09-10'],
            'comparisonCategories': ['2025-09-01', '2025-09-02', '2025-09-10'],
            'series': [{'type': 'line', 'values': [1, 2, 10], 'comparisonValues': [3, 4, 12]}]}
    actual = prepare('period_series', data, {'granularity': 'day'})
    assert len(actual['categories']) == 10
    assert actual['series'][0]['values'] == [1, 2] + [None] * 7 + [10]
    assert actual['series'][0]['comparisonValues'] == [3, 4] + [None] * 7 + [12]
    assert actual['comparisonCategories'][2] is None


def test_irregular_dates_use_temporal_coordinates_but_ordinal_is_preserved():
    data = {'value': 1, 'previous': 1, 'points': [
        {'date': '2026-09-10', 'value': 10}, {'date': '2026-09-01', 'value': 1},
        {'date': '2026-09-02', 'value': 2}]}
    temporal = prepare('kpi_sparkline', data)
    assert temporal['time_mode'] == 'temporal'
    assert [p['value'] for p in temporal['points']] == [1, 2, 10]
    ordinal = prepare('kpi_sparkline', data, {'mode': 'ordinal'})
    assert [p['value'] for p in ordinal['points']] == [10, 1, 2]
    assert ordinal['time_mode'] == 'ordinal'


def test_existing_grain_fills_days_and_preserves_normalized_month_comparison():
    daily = {'grain': 'day', 'categories': ['2026-09-01', '2026-09-02', '2026-09-10'],
             'series': [{'type': 'line', 'values': [1, 2, 10]}]}
    assert len(prepare('period_series', daily)['categories']) == 10
    monthly = {'grain': 'month', 'categories': ['2026-01-01', '2026-02-01', '2026-03-01'],
               'comparisonCategories': ['2025-01-01', '2025-02-01', '2025-03-01'],
               'series': [{'type': 'line', 'values': [1, 2, 3], 'comparisonValues': [3, 4, 5]}]}
    assert prepare('period_series', monthly)['time_mode'] == 'ordinal'


def test_irregular_actual_render_x_uses_elapsed_time_and_daily_gap_breaks_line():
    import re

    from test_visual_fidelity import render

    data = {'categories': ['2026-09-01', '2026-09-02', '2026-09-10'],
            'series': [{'type': 'line', 'values': [1, 2, 10], 'color': '#123456'}]}
    bindings = {'metric': {}, 'date': {}, 'comparison': {}, 'prepared_data': data}
    html = render('period_series', bindings, {'width': 900, 'height': 420})
    line = re.search(r'<polyline[^>]*points="([^"]+)"', html)
    assert line, html
    xs = [float(point.split(',')[0]) for point in line[1].split()]
    assert abs((xs[2] - xs[1]) / (xs[1] - xs[0]) - 8) < 0.02
    bindings['date'] = {'granularity': 'day'}
    daily = render('period_series', bindings, {'width': 900, 'height': 420})
    segments = re.findall(r'<polyline[^>]*points="([^"]+)"', daily)
    assert all(len(points.split()) <= 2 for points in segments)


def test_existing_named_week_buckets_are_ordinal():
    data = {'grain': 'week', 'categories': ['26w01', '26w02'],
            'series': [{'type': 'line', 'values': [1, 2]}]}
    actual = prepare('period_series', data)
    assert actual['time_mode'] == 'ordinal'
    assert actual['categories'] == data['categories']
