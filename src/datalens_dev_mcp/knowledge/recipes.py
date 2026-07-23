from __future__ import annotations

from typing import Any

from datalens_dev_mcp.runtime_resources import RuntimeResourceError, resource_json


RECIPE_REGISTRY_RESOURCE = "templates/datalens/recipes/recipe-registry.json"


def load_recipe_registry() -> dict[str, Any]:
    try:
        return resource_json(RECIPE_REGISTRY_RESOURCE)
    except RuntimeResourceError:
        return {"schema_version": "missing", "recipes": []}


def get_recipe(recipe_id: str) -> dict[str, Any]:
    for item in load_recipe_registry().get("recipes") or []:
        if item.get("recipe_id") == recipe_id:
            return item
    try:
        standalone = resource_json(f"templates/datalens/recipes/{recipe_id}.json")
    except RuntimeResourceError:
        return {}
    if standalone.get("recipe_id") == recipe_id:
        return standalone
    return {}


def select_authoring_recipe(intent_text: str = "", route: str = "", source_type: str = "") -> dict[str, Any]:
    text = " ".join([intent_text or "", route or "", source_type or ""]).lower()
    recipe_id = "advanced_dom_d3" if route == "editor_advanced" else "table_flat_sql"
    blocked_reason = ""
    reference_only_recipe_id = ""
    explicit_schedule = any(
        phrase in text
        for phrase in (
            "resource schedule exception",
            "explicit resource schedule",
            "resource booking conflicts",
            "resource overlap schedule",
            "расписание ресурсов с конфликтами",
            "конфликты бронирования ресурсов",
        )
    )
    standalone_html = any(
        phrase in text
        for phrase in (
            "generate html",
            "html page",
            "standalone html",
            "интерактивная html",
            "сгенерировать html",
        )
    )
    if standalone_html:
        recipe_id = "standalone_html_page"
    elif explicit_schedule:
        recipe_id = "resource_schedule_exception"
    elif "api connector" in text or "api_connector" in text:
        recipe_id = "table_flat_api_connector"
    elif "dataset" in text or "датасет" in text:
        recipe_id = "table_flat_dataset"
    elif "pivot" in text or "свод" in text:
        needs_advanced = any(token in text for token in ("sticky", "grouped", "html", "dom", "advanced exception"))
        if needs_advanced:
            recipe_id = "table_pivot_js"
            reference_only_recipe_id = "table_pivot_advanced_exception"
            blocked_reason = "Advanced HTML pivot is reference-only; use native table_node with nested head.sub."
        else:
            recipe_id = "table_pivot_js"
            blocked_reason = "Advanced pivot exception requires evidence that table_node is insufficient."
    elif any(token in text for token in ("pagination", "footer", "total", "totals", "format", "pinned", "grouped")):
        recipe_id = "table_rich"
    elif "markdown" in text:
        recipe_id = "markdown"
    elif "control" in text or "selector" in text or "селектор" in text:
        recipe_id = "control_dynamic" if "dynamic" in text or "source" in text else "control_static"
    elif "notification" in text or "уведом" in text:
        recipe_id = "notifications"
    elif "link" in text or "action" in text or "связ" in text:
        recipe_id = "links"
    recipe = get_recipe(recipe_id)
    return {
        "recipe_id": recipe_id,
        "recipe": recipe,
        "blocked_advanced_exception_reason": blocked_reason,
        "reference_only_recipe_id": reference_only_recipe_id,
        "selection_basis": "compact_registry_rules",
    }


def compact_recipe_for_payload(recipe: dict[str, Any]) -> dict[str, Any]:
    return {
        "recipe_id": recipe.get("recipe_id") or "",
        "source_contract": recipe.get("source_contract") or "",
        "required_tabs": recipe.get("required_tabs") or [],
        "cardinality_limits": recipe.get("cardinality_limits") or {},
        "algorithmic_bound": recipe.get("algorithmic_bound") or "",
        "validation_checklist": recipe.get("validation_checklist") or [],
        "official_status": recipe.get("official_status") or "",
        "local_policy_status": recipe.get("local_policy_status") or "",
        "implementation_status": recipe.get("implementation_status") or "",
        "publication_status": recipe.get("publication_status") or "",
        "source_traces": recipe.get("source_traces") or [],
    }


def build_recipe_bundle(recipe_id: str) -> dict[str, Any]:
    recipe = get_recipe(recipe_id)
    if not recipe:
        return {"ok": False, "error": {"category": "unknown_recipe", "recipe_id": recipe_id}}
    bundle = recipe.get("executable_bundle") or {}
    if bundle.get("status") != "executable_fixture_tested":
        return {
            "ok": False,
            "recipe_id": recipe_id,
            "status": bundle.get("status") or "not_executable",
            "blocked_reason": recipe.get("implementation_status") or "documented_reference",
        }
    if recipe_id == "standalone_html_page":
        return _standalone_html_recipe_bundle(recipe)
    files = _bundle_files(recipe)
    fixture = _fixture_for(recipe_id)
    expected = _expected_for(recipe_id, fixture)
    files["fixture_input.json"] = fixture
    files["expected_output.json"] = expected
    return {
        "ok": True,
        "recipe_id": recipe_id,
        "route": recipe["route"],
        "files": files,
        "source_traces": recipe.get("source_traces") or [],
        "constraints": {
            "native_recipes_do_not_use_generate_html": not recipe.get("uses_generate_html")
            or recipe_id in {"resource_schedule_exception", "advanced_dom_d3", "notifications"},
            "algorithmic_bound": recipe.get("algorithmic_bound") or "",
            "cardinality_limits": recipe.get("cardinality_limits") or {},
        },
        "validation_checklist": recipe.get("validation_checklist") or [],
    }


def _standalone_html_recipe_bundle(recipe: dict[str, Any]) -> dict[str, Any]:
    from datalens_dev_mcp.html_pages import render_standalone_html_page

    fixture = {
        "title": "Synthetic HTML report",
        "summary": "Portable, responsive, and self-contained.",
        "data": {"metrics": [{"label": "Quality", "value": 100}]},
    }
    rendered = render_standalone_html_page(fixture)
    return {
        "ok": rendered["ok"],
        "recipe_id": recipe["recipe_id"],
        "route": recipe["route"],
        "files": {
            "index.html": rendered["html"],
            "fixture_input.json": fixture,
            "expected_output.json": {
                "strict_validation_ok": True,
                "theme_and_language_supported": True,
                "parent_message_protocols": ["EXPORT", "OPEN_URL"],
                "public_upload_rpc": None,
            },
        },
        "source_traces": recipe.get("source_traces") or [],
        "constraints": {
            "standalone_not_editor_generate_html": True,
            "publication_status": recipe.get("publication_status") or "",
            "bytes": rendered["bytes"],
            "sha256": rendered["sha256"],
        },
        "validation_checklist": recipe.get("validation_checklist") or [],
    }


def _bundle_files(recipe: dict[str, Any]) -> dict[str, Any]:
    recipe_id = recipe["recipe_id"]
    if recipe_id == "resource_schedule_exception":
        from datalens_dev_mcp.editor.standard_templates import GOLDEN_FIXTURE_SOURCE_MODE, load_standard_template_bundle

        bundle = load_standard_template_bundle(
            widget_id="resource_schedule_fixture",
            route="editor_advanced",
            title="Resource schedule fixture",
            family="resource_schedule_exception",
            source_mode=GOLDEN_FIXTURE_SOURCE_MODE,
        )
        if bundle:
            return dict(bundle["tabs"])
    files: dict[str, Any] = {
        "meta.json": {"links": {}, "recipe_id": recipe_id, "route": recipe["route"]},
        "params.js": "module.exports = {lang: 'ru', page: 1, page_size: [100]};\n",
        "sources.js": "module.exports = {data: []};\n",
    }
    if "Config" in recipe.get("required_tabs", []):
        files["config.js"] = "module.exports = {paginator: {enabled: true, limit: 100}, size: 'm'};\n"
    if "Controls" in recipe.get("required_tabs", []):
        files["controls.js"] = "module.exports = {controls: [{id: 'team', type: 'select', labelPlacement: 'left'}]};\n"
    if "Prepare" in recipe.get("required_tabs", []) or recipe_id in {"cross_filter", "links"}:
        files["prepare.js"] = _prepare_js(recipe_id)
    return files


def _fixture_for(recipe_id: str) -> dict[str, Any]:
    rows = [
        {"team": "Alpha", "sprint": "S1", "metric": "Plan", "value": 10, "region": "RU"},
        {"team": "Alpha", "sprint": "S1", "metric": "Fact", "value": 8, "region": "RU"},
        {"team": "Beta", "sprint": "S1", "metric": "Plan", "value": 7, "region": "EN"},
        {"team": "Beta", "sprint": "S1", "metric": "Fact", "value": None, "region": "EN"},
    ]
    return {
        "recipe_id": recipe_id,
        "rows": rows,
        "params": {"team": "Alpha", "lang": "ru"},
        "large_cardinality_threshold": 200,
    }


def _expected_for(recipe_id: str, fixture: dict[str, Any]) -> dict[str, Any]:
    if recipe_id == "table_pivot_js":
        return {
            "head_ids": ["team", "sprint", "group_1", "total"],
            "row_count": 2,
            "footer_total": 25,
            "null_rendered_as": "—",
            "nested_head_depth": 2,
            "page_size_default": 100,
        }
    if recipe_id in {"cross_filter", "links"}:
        return {"relation_count": 1, "safe_parameter_mapping": True}
    return {"head_count_min": 1, "row_count_min": 1}


def _pivot_prepare_js() -> str:
    return r"""function prepare(input) {
  const rows = input.rows || [];
  const config = input.config || {};
  const rowDimensions = Array.isArray(config.row_dimensions) && config.row_dimensions.length ? config.row_dimensions : ['team', 'sprint'];
  const groupField = config.column_group_field || 'column_group';
  const columnField = config.column_dimension || 'metric';
  const valueField = config.value_field || 'value';
  const versionField = config.version_field || 'version';
  const statusField = config.status_field || 'status';
  const urlField = config.url_field || 'url';
  const stateField = config.semantic_state_field || 'semantic_state';
  const doneStatuses = new Set((config.done_statuses || ['done', 'completed', 'closed']).map((value) => String(value).toLowerCase()));
  const maxColumns = Math.min(Number(input.large_cardinality_threshold || 200), 200);
  const maxCells = Math.min(Number(config.max_cells || 20000), 20000);
  function textCompare(left, right) {
    const a = String(left == null ? '' : left);
    const b = String(right == null ? '' : right);
    const aFolded = a.toLowerCase();
    const bFolded = b.toLowerCase();
    if (aFolded < bFolded) return -1;
    if (aFolded > bFolded) return 1;
    return a < b ? -1 : (a > b ? 1 : 0);
  }
  function numericTokenCompare(left, right) {
    const a = String(left == null ? '' : left).match(/\d+/g);
    const b = String(right == null ? '' : right).match(/\d+/g);
    if (!a || !b) return 0;
    for (let index = 0; index < Math.max(a.length, b.length); index += 1) {
      if (a[index] == null) return -1;
      if (b[index] == null) return 1;
      const difference = Number(a[index]) - Number(b[index]);
      if (difference) return difference;
    }
    return 0;
  }
  function semverCompare(left, right) {
    const pattern = /^v?(\d+)\.(\d+)(?:\.(\d+))?(?:-([0-9A-Za-z.-]+))?$/;
    const a = pattern.exec(String(left == null ? '' : left));
    const b = pattern.exec(String(right == null ? '' : right));
    if (!a || !b) return 0;
    for (let index = 1; index <= 3; index += 1) {
      const difference = Number(a[index] || 0) - Number(b[index] || 0);
      if (difference) return difference;
    }
    if (!a[4] && b[4]) return 1;
    if (a[4] && !b[4]) return -1;
    return textCompare(a[4] || '', b[4] || '');
  }
  function compareValues(left, right) {
    return numericTokenCompare(left, right) || semverCompare(left, right) || textCompare(left, right);
  }
  function safeUri(value, allowHttp) {
    const text = String(value == null ? '' : value)
      .replace(/&#(x[0-9a-f]+|\d+);?/gi, (_match, code) => {
        const point = code[0].toLowerCase() === 'x' ? parseInt(code.slice(1), 16) : parseInt(code, 10);
        return Number.isInteger(point) && point >= 0 && point <= 0x10FFFF ? String.fromCodePoint(point) : '\uFFFD';
      })
      .replace(/&colon;/gi, ':')
      .replace(/&tab;/gi, '\t')
      .replace(/&newline;/gi, '\n')
      .replace(/&amp;/gi, '&')
      .trim();
    if (!text || /[\u0000-\u001F\u007F\s]/.test(text) || text.indexOf(String.fromCharCode(92)) !== -1 || text.startsWith('//')) return '';
    if (/^https?:/i.test(text)) {
      try {
        const parsed = new URL(text);
        if (!parsed.hostname || parsed.username || parsed.password) return '';
        if (parsed.protocol === 'https:') return text;
        if (parsed.protocol === 'http:') return allowHttp === true ? text : '';
        return '';
      } catch (_error) { return ''; }
    }
    if (text.includes('://')) return '';
    return /^[A-Za-z][A-Za-z0-9+.-]*:/.test(text) ? '' : text;
  }
  function normalizeValue(value) {
    if (value == null || value === '') return null;
    if (typeof value === 'number') return Number.isFinite(value) ? value : null;
    const text = String(value);
    return /^[-+]?\d+(?:\.\d+)?$/.test(text.trim()) ? Number(text) : text;
  }
  const separator = '\u0000';
  const firstColumnIndex = new Map();
  rows.forEach((row, index) => {
    const key = String(row[groupField] || 'Metrics') + separator + String(row[columnField] || '');
    if (!firstColumnIndex.has(key)) firstColumnIndex.set(key, index);
  });
  const columns = Array.from(firstColumnIndex.keys())
    .map((key) => {
      const parts = key.split(separator);
      return {key, group: parts[0], column: parts[1], firstIndex: firstColumnIndex.get(key)};
    })
    .filter((item) => item.column)
    .sort((left, right) => (
      compareValues(left.group, right.group)
      || compareValues(left.column, right.column)
      || left.firstIndex - right.firstIndex
    ));
  const leafColumnCount = rowDimensions.length + columns.length + 1;
  if (leafColumnCount > maxColumns) throw new Error('cardinality_guard_exceeded');
  const grouped = new Map();
  for (let sourceIndex = 0; sourceIndex < rows.length; sourceIndex += 1) {
    const row = rows[sourceIndex];
    const key = rowDimensions.map((dimension) => String(row[dimension] == null ? '' : row[dimension])).join(separator);
    if (!grouped.has(key)) {
      grouped.set(key, {
        dimensions: rowDimensions.map((dimension) => row[dimension]),
        values: new Map(),
        firstIndex: sourceIndex,
      });
    }
    const target = grouped.get(key);
    const columnKey = String(row[groupField] || 'Metrics') + separator + String(row[columnField] || '');
    if (!target.values.has(columnKey)) target.values.set(columnKey, []);
    target.values.get(columnKey).push({
      value: normalizeValue(row[valueField]),
      version: row[versionField],
      status: String(row[statusField] || ''),
      url: row[urlField],
      state: String(row[stateField] || '').toLowerCase(),
      sourceIndex,
    });
  }
  if (grouped.size * leafColumnCount > maxCells) throw new Error('cell_guard_exceeded');
  const headGroups = [];
  for (let columnIndex = 0; columnIndex < columns.length; columnIndex += 1) {
    const column = columns[columnIndex];
    let group = headGroups.find((item) => item.name === column.group);
    if (!group) {
      group = {id: 'group_' + (headGroups.length + 1), name: column.group, type: 'group', sub: []};
      headGroups.push(group);
    }
    group.sub.push({id: 'value_' + (columnIndex + 1), name: column.column + ' · Value', type: 'text'});
  }
  const head = [
    ...rowDimensions.map((dimension, index) => ({id: dimension, name: dimension, type: 'text', pinned: index === 0, group: index === 0})),
    ...headGroups,
    {id: 'total', name: 'Total', type: 'number'},
  ];
  const body = Array.from(grouped.values()).sort((left, right) => {
    for (let index = 0; index < rowDimensions.length; index += 1) {
      const compared = compareValues(left.dimensions[index], right.dimensions[index]);
      if (compared) return compared;
    }
    return left.firstIndex - right.firstIndex;
  });
  const columnTotals = columns.map(() => 0);
  const statePriority = {critical: 4, warning: 3, change: 2, positive: 1, neutral: 0};
  const outputRows = body.map((row) => {
    let rowTotal = 0;
    const valueCells = columns.map((column, columnIndex) => {
      const entries = (row.values.get(column.key) || []).slice()
        .sort((left, right) => compareValues(left.version, right.version) || left.sourceIndex - right.sourceIndex);
      const done = entries.filter((entry) => doneStatuses.has(entry.status.toLowerCase()));
      const selected = done.length ? [done[done.length - 1]] : entries;
      const displayValues = selected.map((entry) => entry.value == null ? '—' : entry.value);
      const numericTotal = selected.reduce((sum, entry) => sum + (typeof entry.value === 'number' ? entry.value : 0), 0);
      rowTotal += numericTotal;
      columnTotals[columnIndex] += numericTotal;
      const cell = {value: displayValues.length <= 1 ? (displayValues[0] == null ? '—' : displayValues[0]) : displayValues.join(' · ')};
      const state = selected.map((entry) => entry.state)
        .filter((item) => Object.prototype.hasOwnProperty.call(statePriority, item))
        .sort((left, right) => statePriority[right] - statePriority[left])[0] || '';
      if (state) {
        cell.semanticState = state;
        cell.formattedValue = '[' + state.toUpperCase() + '] ' + cell.value;
        cell.css = {'border-left': '3px solid currentColor'};
      }
      if (selected.length === 1) {
        const href = safeUri(selected[0].url, config.allow_http_links === true);
        if (href) cell.link = {href};
        else if (selected[0].url) cell.linkFallback = {render_as: 'plain_text', reason: 'unsafe_uri'};
      }
      return cell;
    });
    return {cells: [...row.dimensions.map((value) => ({value: value == null ? '—' : value})), ...valueCells, {value: rowTotal}]};
  });
  const footerTotal = columnTotals.reduce((sum, value) => sum + value, 0);
  return {
    head,
    rows: outputRows,
    pagination: {default_page_size: 100, minimum: 1, maximum: 200},
    footer: {cells: [
      {value: 'Total'},
      ...rowDimensions.slice(1).map(() => ({value: ''})),
      ...columnTotals.map((value) => ({value})),
      {value: footerTotal},
    ]},
  };
}
module.exports = prepare;
"""


def _prepare_js(recipe_id: str) -> str:
    if recipe_id == "table_pivot_js":
        return _pivot_prepare_js()
    if recipe_id in {"cross_filter", "links"}:
        return (
            "module.exports = function prepare() { "
            "return {relations: [{source: 'chart_a', target: 'chart_b'}]}; };\n"
        )
    if recipe_id in {"advanced_dom_d3", "table_pivot_advanced_exception", "notifications"}:
        return (
            "module.exports = {render: Editor.wrapFn({args: [], fn: function() { "
            "return Editor.generateHtml('<div data-id=\"semantic-recipe\"></div>'); }} )};\n"
        )
    return (
        "module.exports = function prepare(input) { const rows = input.rows || []; "
        "return {head: [{id: 'team', name: 'Team'}], rows: rows.map((row) => ({cells: [{value: row.team || ''}]}))}; };\n"
    )
