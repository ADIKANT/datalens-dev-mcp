#!/usr/bin/env node
import fs from 'node:fs';
import vm from 'node:vm';

const states = {
  full: {name: 'full', rows: [{id: 1, value: 10}, {id: 2, value: 20}]},
  'partial-null': {name: 'partial-null', rows: [{id: 1, value: null}, {id: 2, value: 20}]},
  'empty-expected': {name: 'empty-expected', rows: [], expectedEmpty: true},
  'empty-unexpected': {name: 'empty-unexpected', rows: [], expectedEmpty: false},
  'single-row': {name: 'single-row', rows: [{id: 1, value: 10}]},
  'long-labels': {name: 'long-labels', rows: [{id: 1, label: 'A very long synthetic label for contract testing'}]},
  'high-cardinality': {name: 'high-cardinality', rows: Array.from({length: 101}, (_, index) => ({id: index + 1}))},
  'pagination-boundary': {name: 'pagination-boundary', rows: Array.from({length: 20}, (_, index) => ({id: index + 1}))},
};

function stable(value) {
  if (Array.isArray(value)) return value.map(stable);
  if (value && typeof value === 'object') {
    return Object.fromEntries(Object.keys(value).sort().map((key) => [key, stable(value[key])]));
  }
  return value;
}

function opaque(value) {
  const text = String(value || '').replace(/\s/g, '').toLowerCase();
  return text && text !== 'transparent' && text !== 'none' && !text.endsWith(',0)') && !text.endsWith(',0.0)');
}

function evaluateOutput(output, expectations, state) {
  const failures = [];
  const legend = Array.isArray(output.legend) ? output.legend : [];
  if (expectations.legend_series && JSON.stringify(legend) !== JSON.stringify(expectations.legend_series)) {
    failures.push('legend_series_exact');
  }
  if (expectations.sticky_header_opaque && output.header?.sticky === true && !opaque(output.header?.background)) {
    failures.push('sticky_header_opaque');
  }
  if (expectations.pagination_page_size && output.pagination?.pageSize !== expectations.pagination_page_size) {
    failures.push('pagination_page_size');
  }
  if (state.name === 'pagination-boundary' && expectations.pagination_page_size) {
    const expectedPages = Math.ceil(state.rows.length / expectations.pagination_page_size);
    if (output.pagination?.pageCount !== expectedPages) failures.push('pagination_boundary');
  }
  if (state.name === 'partial-null' && expectations.partial_indicator_visible && output.indicators?.partialVisible !== true) {
    failures.push('partial_indicator_visible');
  }
  if (state.name === 'empty-expected' && (output.emptyState?.visible !== true || output.emptyState?.expected !== true)) {
    failures.push('expected_empty_state');
  }
  if (state.name === 'empty-unexpected' && (output.emptyState?.visible !== true || output.emptyState?.expected !== false)) {
    failures.push('unexpected_empty_state');
  }
  if (expectations.selector_ids) {
    const selectorIds = (output.selectors || []).map((item) => item.id);
    if (JSON.stringify(selectorIds) !== JSON.stringify(expectations.selector_ids)) failures.push('selector_contract');
  }
  return failures;
}

function runFixture(fixture) {
  const issues = [];
  const results = [];
  for (const viewport of fixture.viewports || []) {
    for (const stateName of fixture.data_states || []) {
      for (const theme of fixture.themes || []) {
        const state = states[stateName];
        if (!state) {
          issues.push(`unknown_data_state:${stateName}`);
          continue;
        }
        const module = {exports: {}};
        const Editor = {
          getParam: (name) => fixture.params?.[name],
          getLoadedData: () => state.rows,
        };
        const context = vm.createContext(
          {module, exports: module.exports, Editor, console: {log() {}, error() {}}},
          {codeGeneration: {strings: false, wasm: false}},
        );
        try {
          new vm.Script(String(fixture.prepare_source || ''), {timeout: 1000}).runInContext(context, {timeout: 1000});
          const exported = module.exports;
          const callable = typeof exported === 'function' ? exported : exported.prepare || exported.render;
          if (typeof callable !== 'function') throw new Error('prepare_source must export a function');
          const output = stable(callable({Editor, loadedData: state.rows, viewport, theme, state}));
          const failures = evaluateOutput(output || {}, fixture.expectations || {}, state);
          results.push({viewport, state: stateName, theme, passed: failures.length === 0, failures, output});
          for (const failure of failures) issues.push(`${viewport.id}:${stateName}:${theme}:${failure}`);
        } catch (error) {
          issues.push(`${viewport.id}:${stateName}:${theme}:runtime:${error.name}`);
        }
      }
    }
  }
  return {
    schema_id: 'render_contract_result',
    fixture_id: fixture.fixture_id || '',
    ok: issues.length === 0,
    status: issues.length === 0 ? 'passed' : 'failed',
    case_count: results.length,
    passed_count: results.filter((item) => item.passed).length,
    issues: [...new Set(issues)],
    results,
  };
}

function source(mode = 'pass') {
  return `module.exports = ({state}) => ({
    header: {sticky: true, background: ${JSON.stringify(mode === 'transparent' ? 'transparent' : '#ffffff')}},
    legend: ${JSON.stringify(mode === 'extra-legend' ? ['actual', 'extra'] : ['actual'])},
    series: [{id: 'actual', visible: true}],
    pagination: {pageSize: ${mode === 'wrong-pagination' ? 9 : 10}, pageCount: Math.ceil(state.rows.length / 10)},
    selectors: [{id: 'period'}],
    emptyState: {visible: state.rows.length === 0, expected: state.expectedEmpty === true},
    indicators: {partialVisible: ${mode === 'hidden-partial' ? 'false' : 'true'}}
  });`;
}

function selfTest() {
  const base = {
    schema_id: 'render_contract_fixture', fixture_id: 'self-test',
    viewports: [{id: 'compact', width: 320, height: 220}],
    data_states: Object.keys(states), themes: ['light', 'dark', 'contrast'], params: {},
    expectations: {legend_series: ['actual'], sticky_header_opaque: true, pagination_page_size: 10, partial_indicator_visible: true, selector_ids: ['period']},
  };
  const passing = runFixture({...base, prepare_source: source('pass')});
  const negativeModes = ['transparent', 'extra-legend', 'hidden-partial', 'wrong-pagination'];
  const negatives = Object.fromEntries(negativeModes.map((mode) => [mode, runFixture({...base, fixture_id: mode, prepare_source: source(mode)})]));
  const ok = passing.ok && Object.values(negatives).every((item) => item.ok === false);
  return {schema_id: 'render_contract_self_test', ok, passing, negative_rules: Object.fromEntries(Object.entries(negatives).map(([key, value]) => [key, value.issues]))};
}

let output;
if (process.argv.includes('--self-test')) {
  output = selfTest();
} else if (process.argv.includes('--stdin')) {
  output = runFixture(JSON.parse(fs.readFileSync(0, 'utf8')));
} else {
  const path = process.argv[2];
  if (!path) throw new Error('use --self-test, --stdin, or provide a fixture path');
  output = runFixture(JSON.parse(fs.readFileSync(path, 'utf8')));
}
process.stdout.write(`${JSON.stringify(output)}\n`);
process.exitCode = output.ok ? 0 : 1;
