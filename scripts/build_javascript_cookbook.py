#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from datalens_dev_mcp.editor.bundle import generate_editor_bundle  # noqa: E402
from datalens_dev_mcp.editor.reference_runtime import (  # noqa: E402
    compile_standard_dashboard_renderer,
    validate_standard_dashboard_renderer,
)
from datalens_dev_mcp.editor.render_contract import (  # noqa: E402
    render_contract_to_dict,
    resolve_dashboard_render_contract,
    build_renderer_visual_spec,
)
from datalens_dev_mcp.editor.title_contract import normalize_title_contract  # noqa: E402


CATALOG_PATH = ROOT / "config" / "javascript_cookbook.json"
CATALOG_SCHEMA_PATH = ROOT / "config" / "javascript_cookbook.schema.json"
OUTPUT_ROOT = ROOT / "docs" / "cookbook"
APP_SOURCE = ROOT / "templates" / "cookbook" / "app.js"
STYLE_SOURCE = ROOT / "templates" / "cookbook" / "styles.css"
SCHEMA_ID = "javascript_cookbook"
LOCALES = ("ru", "en")
EXPECTED_ROUTE_COUNTS = {"editor_advanced": 25, "editor_table": 4, "editor_js_control": 5}
EXPECTED_TABS = {
    "editor_advanced": ["meta.json", "params.js", "sources.js", "controls.js", "prepare.js"],
    "editor_table": ["meta.json", "params.js", "sources.js", "prepare.js", "config.js"],
    "editor_js_control": ["meta.json", "params.js", "sources.js", "controls.js"],
}
EXPECTED_FAMILIES = {
    "kpi_value_only",
    "kpi_value_delta",
    "kpi_value_sparkline",
    "kpi_value_delta_sparkline",
    "line_chart",
    "multiline_chart",
    "area_completion",
    "vertical_bar_time_bucket",
    "combo_time_series_combo",
    "horizontal_bar",
    "grouped_bar",
    "stacked_100",
    "bullet_assignees",
    "heatmap",
    "waterfall",
    "funnel_snapshot",
    "sankey_status_flow",
    "histogram",
    "box_plot",
    "scatter",
    "bubble",
    "pie",
    "donut",
    "treemap",
    "table_node",
    "search_selector",
    "date_range_selector",
    "selector_family_static",
    "selector_family_dynamic",
    "selector_group",
}
SOURCE_BACKED_SELECTORS = {"selector_family_dynamic", "selector_group"}
LOCALIZED_KEYS = {"ru", "en"}


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def pretty_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def localize_value(value: Any, lang: str) -> Any:
    if isinstance(value, dict):
        if set(value) == LOCALIZED_KEYS:
            return localize_value(value[lang], lang)
        return {key: localize_value(item, lang) for key, item in value.items()}
    if isinstance(value, list):
        return [localize_value(item, lang) for item in value]
    return value


def load_catalog() -> dict[str, Any]:
    catalog = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    issues = validate_catalog(catalog)
    if issues:
        raise ValueError("invalid JavaScript cookbook catalog: " + "; ".join(issues))
    return catalog


def field_contract(catalog: dict[str, Any], key: str, lang: str) -> dict[str, Any]:
    raw = catalog["field_glossary"].get(key)
    if not isinstance(raw, dict):
        raise ValueError(f"unknown source field glossary key: {key}")
    result = localize_value(raw, lang)
    result["key"] = key
    result["alias"] = str(raw.get("alias") or key)
    return result


def recipe_fields(catalog: dict[str, Any], recipe: dict[str, Any], lang: str) -> list[dict[str, Any]]:
    fields = [field_contract(catalog, str(key), lang) for key in recipe["source_columns"]]
    if recipe["family"] in SOURCE_BACKED_SELECTORS:
        for field in fields:
            if field["alias"] == "value":
                option = field_contract(catalog, "option_value", lang)
                field.update(option)
    return fields


def validate_catalog(catalog: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    if catalog.get("schema_id") != SCHEMA_ID:
        issues.append(f"schema_id must be {SCHEMA_ID}")
    if catalog.get("profile_id") != "standard_dashboard":
        issues.append("profile_id must be standard_dashboard")
    if catalog.get("locales") != list(LOCALES) or catalog.get("default_locale") not in LOCALES:
        issues.append("locales must be ru/en with a valid default_locale")
    pages_url = str(catalog.get("pages_url") or "")
    if not pages_url.startswith("https://") or not pages_url.endswith("/"):
        issues.append("pages_url must be an absolute HTTPS directory URL")
    if catalog.get("source_modes") != ["dataset", "clickhouse"]:
        issues.append("source_modes must be dataset/clickhouse")
    try:
        schema = json.loads(CATALOG_SCHEMA_PATH.read_text(encoding="utf-8"))
        if schema.get("properties", {}).get("schema_id", {}).get("const") != SCHEMA_ID:
            issues.append("catalog JSON Schema does not bind the canonical schema_id")
    except (OSError, json.JSONDecodeError):
        issues.append("catalog JSON Schema is missing or invalid")
    recipes = catalog.get("recipes")
    if not isinstance(recipes, list):
        return [*issues, "recipes must be an array"]
    if len(recipes) != 34:
        issues.append("catalog must contain exactly 34 recipes")
    pairs: set[tuple[str, str]] = set()
    slugs: set[str] = set()
    route_counts: dict[str, int] = {key: 0 for key in EXPECTED_ROUTE_COUNTS}
    families: set[str] = set()
    glossary = catalog.get("field_glossary") if isinstance(catalog.get("field_glossary"), dict) else {}
    for index, recipe in enumerate(recipes):
        if not isinstance(recipe, dict):
            issues.append(f"recipes[{index}] must be an object")
            continue
        slug = str(recipe.get("slug") or "")
        variant = str(recipe.get("variant") or "")
        family = str(recipe.get("family") or "")
        route = str(recipe.get("route") or "")
        pair = (slug, variant)
        if not slug or slug in slugs:
            issues.append(f"recipes[{index}].slug must be unique and non-empty")
        if not variant or pair in pairs:
            issues.append(f"{slug}.variant must make slug + variant unique")
        if route not in EXPECTED_TABS:
            issues.append(f"{slug}.route is unsupported")
        else:
            route_counts[route] += 1
            if recipe.get("tabs") != EXPECTED_TABS[route]:
                issues.append(f"{slug}.tabs do not match {route}")
        for key in ("title", "summary", "use_case", "behavior"):
            localized = recipe.get(key)
            if not isinstance(localized, dict) or set(localized) != LOCALIZED_KEYS:
                issues.append(f"{slug}.{key} must contain only ru and en")
        source_keys = recipe.get("source_columns")
        if not isinstance(source_keys, list) or len(source_keys) != len(set(source_keys)):
            issues.append(f"{slug}.source_columns must be a unique array")
        else:
            aliases: list[str] = []
            for key in source_keys:
                field = glossary.get(str(key))
                if not isinstance(field, dict):
                    issues.append(f"{slug} references unknown source field {key}")
                    continue
                aliases.append(str(field.get("alias") or key))
            if len(aliases) != len(set(aliases)):
                issues.append(f"{slug}.source_columns resolve to duplicate aliases")
        if not isinstance(recipe.get("fixture_rows"), list):
            issues.append(f"{slug}.fixture_rows must be an array")
        if not isinstance(recipe.get("params"), dict):
            issues.append(f"{slug}.params must be an object")
        slugs.add(slug)
        pairs.add(pair)
        families.add(family)
    if route_counts != EXPECTED_ROUTE_COUNTS:
        issues.append(f"route counts differ: {route_counts}")
    if not EXPECTED_FAMILIES.issubset(families):
        issues.append("catalog does not contain every public cookbook family")
    if "resource_schedule_exception" in families or any(item.startswith("md_") for item in families):
        issues.append("specialized schedule and Markdown families are excluded")
    cases = catalog.get("cases")
    if not isinstance(cases, list) or len(cases) != 3:
        issues.append("catalog must contain exactly three cases")
    else:
        case_slugs: set[str] = set()
        for case in cases:
            slug = str(case.get("slug") or "")
            if not slug or slug in case_slugs:
                issues.append("case slugs must be unique and non-empty")
            case_slugs.add(slug)
            objects = case.get("objects") if isinstance(case.get("objects"), list) else []
            object_ids = {str(item.get("id") or "") for item in objects if isinstance(item, dict)}
            for parameter in case.get("params") or []:
                owner = str(parameter.get("owner") or "")
                readers = {str(item) for item in parameter.get("readers") or []}
                if owner not in object_ids or not readers or not readers.issubset(object_ids):
                    issues.append(f"{slug}: parameter graph references unknown objects")
            for item in objects:
                recipe_slug = str(item.get("recipe") or "")
                if recipe_slug and recipe_slug not in slugs:
                    issues.append(f"{slug}: object references unknown recipe {recipe_slug}")
    return issues


def _strip_js_comments(value: str) -> str:
    value = re.sub(r"/\*.*?\*/", "", value, flags=re.DOTALL)
    value = re.sub(r"^[ \t]*//[^\n]*(?:\n|$)", "", value, flags=re.MULTILINE)
    return re.sub(r"\n{3,}", "\n\n", value).strip() + "\n"


def _strip_js_strings_and_comments(value: str) -> str:
    value = _strip_js_comments(value)
    value = re.sub(r"'(?:\\.|[^'\\])*'", "''", value)
    value = re.sub(r'"(?:\\.|[^"\\])*"', '""', value)
    value = re.sub(r"`(?:\\.|[^`\\])*`", "``", value, flags=re.DOTALL)
    return re.sub(r"\s+", " ", value).strip()


def _js_banner(tab: str, lang: str, route: str) -> str:
    if lang == "ru":
        messages = {
            "sources.js": "Обязательная точка изменения: подключите свой источник и сохраните документированные выходные aliases.",
            "meta.json": "Укажите ссылки на dataset или connection, созданные в Meta.",
            "params.js": "Готовые значения параметров. Не меняйте их при обычном копировании рецепта.",
            "controls.js": "Готовая конфигурация контролов и их связи с Params.",
            "config.js": "Готовая нативная конфигурация table_node: пагинация, размеры и прокрутка.",
            "prepare.js": "Защищённая подготовка модели и рендер. Обычный перенос не требует изменений.",
        }
        return (
            "/**\n"
            f" * {messages.get(tab, 'Готовая вкладка DataLens Editor.')}\n"
            f" * Route: {route}. Технические имена параметров и aliases оставлены без перевода.\n"
            " */\n"
        )
    messages = {
        "sources.js": "Required edit point: connect your source and preserve the documented output aliases.",
        "meta.json": "Declare the dataset or connection references used by Meta.",
        "params.js": "Ready parameter values. Keep them unchanged for a normal recipe transfer.",
        "controls.js": "Ready control configuration and Params bindings.",
        "config.js": "Ready native table_node configuration: pagination, sizing, and scrolling.",
        "prepare.js": "Protected model preparation and renderer. A normal transfer does not require edits.",
    }
    return (
        "/**\n"
        f" * {messages.get(tab, 'Ready DataLens Editor tab.')}\n"
        f" * Route: {route}. Technical parameter names and aliases are language-neutral.\n"
        " */\n"
    )


def _customize_block(lang: str) -> str:
    note = (
        "Необязательная настройка: меняйте значения только внутри этого блока."
        if lang == "ru"
        else "Optional customization: change values only inside this block."
    )
    empty = "Нет данных" if lang == "ru" else "No data"
    return (
        f"// CUSTOMIZE — {note}\n"
        "const COOKBOOK_CUSTOMIZE = Object.freeze({\n"
        "  palette: ['#2B75E2', '#F2994A', '#008A91', '#7A5AF8', '#D92D20'],\n"
        "  numberFormat: 'decimal1',\n"
        "  unit: '',\n"
        f"  emptyLabel: {json.dumps(empty, ensure_ascii=False)},\n"
        "});\n\n"
    )


def _localize_visible_js(value: str, lang: str) -> str:
    if lang == "en":
        return value
    replacements = {
        "'Comparison'": "'Сравнение'",
        "'COMPARISON'": "'СРАВНЕНИЕ'",
        "'Value'": "'Значение'",
        "'All'": "'Все'",
        "'No data'": "'Нет данных'",
        "'Adjust sources.js'": "'Проверьте sources.js'",
        "'Check sources.js'": "'Проверьте sources.js'",
        "'Check sources.js and active Params'": "'Проверьте sources.js и активные Params'",
        "'Identifier'": "'Идентификатор'",
        "'Object'": "'Объект'",
        "'Status'": "'Статус'",
        "'Owner'": "'Владелец'",
        "'Updated'": "'Обновлено'",
        "'Amount'": "'Сумма'",
        "'Details'": "'Подробнее'",
        "'Item'": "'Строка'",
        "'Category'": "'Категория'",
        "'Completion'": "'Выполнение'",
        "'Completed'": "'Выполнено'",
        "'Total'": "'Всего'",
        "'Progress'": "'Прогресс'",
        "'Open'": "'Открыть'",
        "'Ready'": "'Готово'",
        "'Needs attention'": "'Требует внимания'",
        "'In review'": "'На проверке'",
        "'Error'": "'Ошибка'",
        "'Failed'": "'Не выполнено'",
        "'Unknown'": "'Неизвестно'",
        "'N/A'": "'Нет данных'",
        "'n/a'": "'нет данных'",
        "'DAY'": "'ДЕНЬ'",
        "'WEEK'": "'НЕДЕЛЯ'",
        "'MONTH'": "'МЕСЯЦ'",
        "'SAME DAYS PREVIOUS WEEK'": "'ТЕ ЖЕ ДНИ ПРОШЛОЙ НЕДЕЛИ'",
        "'PREVIOUS MONTH'": "'ПРОШЛЫЙ МЕСЯЦ'",
        "'PREVIOUS EQUAL PERIOD'": "'ПРОШЛЫЙ РАВНЫЙ ПЕРИОД'",
        "'PERIOD'": "'ПЕРИОД'",
        "'Detail table'": "'Детальная таблица'",
        "'Status table'": "'Таблица состояний'",
        "'Grouped summary'": "'Сгруппированная сводка'",
        "'Standard table'": "'Стандартная таблица'",
        ">Comparison<": ">Сравнение<",
        " · comparison": " · сравнение",
        "NO FLOW DATA": "НЕТ ДАННЫХ О ПОТОКАХ",
        "positive total required": "нужен положительный итог",
        "100% stack requires non-negative values": "для 100% stacked нужны неотрицательные значения",
        "VS ${": "СРАВНЕНИЕ · ${",
        ">VS<": ">СРАВНЕНИЕ<",
        ">CURRENT<": ">ТЕКУЩИЙ ПЕРИОД<",
        "Change:": "Изменение:",
        "'Stable row key'": "'Стабильный ключ строки'",
        "'Primary display name'": "'Основное название'",
        "'ISO-8601 source value'": "'Исходное значение ISO-8601'",
        "'Ordered cumulative deltas with start and end positions.'": "'Последовательные изменения с начальной и конечной позициями.'",
        "'Sorted comparison with zero baseline and direct labels.'": "'Отсортированное сравнение с нулевой осью и прямыми подписями.'",
        "'Distribution or relationship with explicit numeric fields.'": "'Распределение или связь с явными числовыми полями.'",
        "'Small part-to-whole set; prefer bars for ranking.'": "'Небольшой состав целого; для рейтинга используйте столбцы.'",
        "'Flow chart requires explicit source, target, and positive value.'": (
            "'Для потока нужны явные source, target и положительное value.'"
        ),
        "'category_cap_exceeded'": "'слишком_много_категорий'",
        "'invalid_or_negative_part'": "'некорректная_или_отрицательная_часть'",
        "'positive_total_required'": "'нужен_положительный_итог'",
        "'cyclic_flow'": "'циклический_поток'",
        "'flow_rows_require_source_target_and_positive_value'": "'нужны_source_target_и_положительное_value'",
        "N/A · cyclic_flow": "N/A · циклический_поток",
    }
    for source, target in replacements.items():
        value = value.replace(source, target)
    return value


def localize_js(value: str, *, tab: str, lang: str, route: str, variant: str) -> str:
    value = _localize_visible_js(value, lang)
    selected_notes = re.findall(rf"@cookbook-locale\s+{lang}\s+([^\n*]+)", value)
    value = _strip_js_comments(value)
    prefix = _js_banner(tab, lang, route)
    if selected_notes:
        prefix += "\n".join(f"// {note.strip()}" for note in selected_notes) + "\n"
    if tab == "prepare.js":
        prefix += _customize_block(lang)
        value = value.replace(
            "const colors = ['#2B75E2', '#F2994A', '#008A91', '#7A5AF8', '#D92D20'];",
            "const colors = COOKBOOK_CUSTOMIZE.palette;",
        )
        value = value.replace("format: 'decimal1'", "format: COOKBOOK_CUSTOMIZE.numberFormat")
        value = value.replace("unit: ''", "unit: COOKBOOK_CUSTOMIZE.unit")
    rendered = prefix + value.lstrip()
    return "\n".join(line.rstrip() for line in rendered.split("\n"))


def _params_js(params: dict[str, Any], lang: str, route: str) -> str:
    value = "module.exports = " + json.dumps(params, ensure_ascii=False, indent=2, sort_keys=True) + ";\n"
    return _js_banner("params.js", lang, route) + value


def _cumulative_prepare(value: str) -> str:
    needle = "const profileRows = profileLoadedRows('rows');"
    replacement = """const profileInputRows = profileLoadedRows('rows')
  .filter((row) => row.bucket && profileFinite(row.increment) !== null && profileFinite(row.increment) !== 0)
  .sort((left, right) => String(left.bucket).localeCompare(String(right.bucket)));
let profileCumulativeValue = 0;
const profileRows = profileInputRows.map((row) => {
  profileCumulativeValue += profileFinite(row.increment);
  return {...row, value: profileCumulativeValue};
});"""
    if needle not in value:
        raise ValueError("cumulative-line: protected adapter insertion point is missing")
    return value.replace(needle, replacement, 1)


def compile_recipe(catalog: dict[str, Any], recipe: dict[str, Any], lang: str = "en") -> dict[str, Any]:
    if lang not in LOCALES:
        raise ValueError(f"unsupported locale: {lang}")
    family = str(recipe["family"])
    route = str(recipe["route"])
    variant = str(recipe["variant"])
    fields = recipe_fields(catalog, recipe, lang)
    aliases = [str(field["alias"]) for field in fields]
    needs_dataset = route in {"editor_advanced", "editor_table"} or family in SOURCE_BACKED_SELECTORS
    selector_contract = localize_value(recipe.get("selector_contract"), lang)
    title_contract = normalize_title_contract(
        route=route,
        family=family,
        display_title=str(recipe["title"][lang]),
        hint=str(recipe["summary"][lang]),
    )
    if not title_contract.get("ok"):
        raise ValueError(f"{recipe['slug']}/{lang}: invalid title contract")
    render_contract = resolve_dashboard_render_contract(profile_id=str(catalog["profile_id"]), family=family)
    visual_spec = build_renderer_visual_spec(
        {}, render_contract=render_contract, title_contract=title_contract, comparison_enabled="delta" in family
    )
    bundle = generate_editor_bundle(
        widget_id=f"cookbook_{recipe['slug']}",
        route=route,
        title=str(recipe["title"][lang]),
        dataset_alias=str(catalog["dataset_placeholder"]) if needs_dataset else None,
        columns=aliases if needs_dataset else None,
        selector_contract=selector_contract,
        family=family,
        visual_spec=visual_spec,
    )
    bundle["title_contract"] = title_contract
    bundle["native_metadata"] = dict(title_contract["native_metadata"])
    compiled = compile_standard_dashboard_renderer(
        bundle,
        render_contract=render_contract_to_dict(render_contract),
        title_contract=title_contract,
    )
    validation = validate_standard_dashboard_renderer(compiled)
    if not validation.get("ok"):
        raise ValueError(f"{recipe['slug']}/{lang}: compiled renderer is invalid: {validation.get('issues')}")
    raw_tabs = dict(compiled.get("tabs") or {})
    expected_tabs = list(recipe["tabs"])
    missing = [name for name in expected_tabs if not str(raw_tabs.get(name) or "").strip()]
    unexpected = sorted(set(raw_tabs) - set(expected_tabs))
    if missing or unexpected:
        raise ValueError(f"{recipe['slug']}/{lang}: tab mismatch; missing={missing}, unexpected={unexpected}")
    raw_tabs["params.js"] = "module.exports = " + json.dumps(recipe["params"], ensure_ascii=False, indent=2, sort_keys=True) + ";\n"
    if aliases and needs_dataset:
        raw_tabs["sources.js"] = (
            "const {buildSource} = require('libs/dataset/v2');\n\n"
            "module.exports = {\n"
            "  rows: buildSource({\n"
            "    datasetId: Editor.getId('dataset'),\n"
            f"    columns: {json.dumps(aliases, ensure_ascii=False)},\n"
            "  }),\n"
            "};\n"
        )
    if variant == "cumulative":
        raw_tabs["prepare.js"] = _cumulative_prepare(raw_tabs["prepare.js"])
    canonical_parts: dict[str, Any] = {}
    for name in expected_tabs:
        if name.endswith(".js"):
            canonical_parts[name] = _strip_js_strings_and_comments(raw_tabs[name])
        else:
            canonical_parts[name] = json.loads(raw_tabs[name])
    canonical_hash = sha256_text(canonical_json(canonical_parts))
    tabs = {
        name: localize_js(raw_tabs[name], tab=name, lang=lang, route=route, variant=variant) if name.endswith(".js") else raw_tabs[name]
        for name in expected_tabs
    }
    fixture_rows = localize_value(recipe["fixture_rows"], lang)
    params = localize_value(recipe["params"], lang)
    support_files = build_support_files(catalog, recipe, tabs=tabs, fields=fields, fixture_rows=fixture_rows, params=params, lang=lang)
    structure_hashes = {name: sha256_text(_strip_js_strings_and_comments(raw_tabs[name])) for name in expected_tabs if name.endswith(".js")}
    provenance = compiled.get("template_provenance") if isinstance(compiled.get("template_provenance"), dict) else {}
    return {
        "slug": str(recipe["slug"]),
        "variant": variant,
        "family": family,
        "route": route,
        "group": str(recipe["group"]),
        "lang": lang,
        "title": str(recipe["title"][lang]),
        "summary": str(recipe["summary"][lang]),
        "use_case": str(recipe["use_case"][lang]),
        "behavior": str(recipe["behavior"][lang]),
        "tooltip": str(recipe["tooltip"]),
        "tab_order": expected_tabs,
        "tabs": tabs,
        "support_files": support_files,
        "source_contract": fields,
        "fixture_rows": fixture_rows,
        "params": params,
        "selector_contract": selector_contract,
        "canonical_executable_sha256": canonical_hash,
        "structure_hashes": structure_hashes,
        "template_provenance": {
            "renderer_kind": str(provenance.get("renderer_kind") or ""),
            "canonical_runtime_sha256": str(provenance.get("canonical_runtime_sha256") or ""),
            "canonical_adapter_sha256": str(provenance.get("canonical_adapter_sha256") or ""),
        },
    }


def build_support_files(
    catalog: dict[str, Any],
    recipe: dict[str, Any],
    *,
    tabs: dict[str, str],
    fields: list[dict[str, Any]],
    fixture_rows: list[dict[str, Any]],
    params: dict[str, Any],
    lang: str,
) -> dict[str, str]:
    meta = json.loads(tabs["meta.json"])
    properties: dict[str, Any] = {
        "meta": {
            "type": "object",
            "description": (
                "Ссылки DataLens Editor; меняйте placeholders." if lang == "ru" else "DataLens Editor links; replace placeholders."
            ),
            "additionalProperties": True,
        },
        "params": {"type": "object", "additionalProperties": {"type": "array"}},
    }
    required = ["meta", "params"]
    if fields:
        row_properties: dict[str, Any] = {}
        row_required: list[str] = []
        for field in fields:
            field_type: str | list[str] = field["type"]
            if field["nullable"]:
                field_type = [field_type, "null"]
            else:
                row_required.append(field["alias"])
            row_properties[field["alias"]] = {
                "type": field_type,
                "description": field["meaning"],
                "examples": [field["example"]],
            }
        properties["rows"] = {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": row_required,
                "properties": row_properties,
            },
        }
        required.insert(0, "rows")
    schema = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": recipe["title"][lang],
        "type": "object",
        "additionalProperties": False,
        "required": required,
        "properties": properties,
    }
    example: dict[str, Any] = {"meta": meta, "params": params}
    if fields:
        example["rows"] = fixture_rows
    return {"schema.json": pretty_json(schema), "example_input.json": pretty_json(example)}


def _case_defaults(case: dict[str, Any]) -> dict[str, Any]:
    return {str(item["name"]): list(item["default"]) for item in case["params"]}


def _case_control_descriptors(kind: str, lang: str) -> list[dict[str, Any]]:
    copy = {
        "ru": {
            "period": "Период",
            "comparison": "Сравнение",
            "step": "Шаг по времени",
            "category": "Категория",
            "status": "Статус",
            "all": "Все",
            "previous": "Предыдущий период",
            "year": "Год назад",
            "auto": "Авто",
            "day": "День",
            "week": "Неделя",
            "month": "Месяц",
            "ready": "Готово",
            "warning": "Требует внимания",
        },
        "en": {
            "period": "Period",
            "comparison": "Comparison",
            "step": "Time step",
            "category": "Category",
            "status": "Status",
            "all": "All",
            "previous": "Previous period",
            "year": "Previous year",
            "auto": "Auto",
            "day": "Day",
            "week": "Week",
            "month": "Month",
            "ready": "Ready",
            "warning": "Needs attention",
        },
    }[lang]
    period = {"type": "range-datepicker", "paramFrom": "dateFrom", "paramTo": "dateTo", "label": copy["period"], "width": "94%"}
    if kind == "period_comparison":
        return [
            period,
            {
                "type": "select",
                "param": "comparisonMethod",
                "label": copy["comparison"],
                "width": "46%",
                "content": [{"title": copy["previous"], "value": "previous_period"}, {"title": copy["year"], "value": "previous_year"}],
            },
            {
                "type": "select",
                "param": "timeStep",
                "label": copy["step"],
                "width": "46%",
                "content": [{"title": copy[key], "value": key} for key in ("auto", "day", "week", "month")],
            },
        ]
    controls = [
        period,
        {
            "type": "select",
            "param": "category",
            "label": copy["category"],
            "searchable": True,
            "width": "46%",
            "content": [{"title": copy["all"], "value": ""}, {"title": "A", "value": "a"}, {"title": "B", "value": "b"}],
        },
    ]
    if kind == "filters_detail":
        controls.append(
            {
                "type": "select",
                "param": "status",
                "label": copy["status"],
                "multiselect": True,
                "width": "46%",
                "content": [{"title": copy["ready"], "value": "ready"}, {"title": copy["warning"], "value": "warning"}],
            }
        )
    return controls


def _case_controls_js(kind: str, lang: str, route: str) -> str:
    descriptors = _case_control_descriptors(kind, lang)
    value = "module.exports = {controls: " + json.dumps(descriptors, ensure_ascii=False, indent=2) + "};\n"
    return _js_banner("controls.js", lang, route) + value


def _case_meta(mode: str, catalog: dict[str, Any]) -> str:
    links = (
        {"dataset": catalog["dataset_placeholder"]} if mode == "dataset" else {"defaultConnection": "replace_with_clickhouse_connection_id"}
    )
    return pretty_json({"links": links})


def _dataset_source(aliases: list[str], lang: str, route: str) -> str:
    if not aliases:
        return _js_banner("sources.js", lang, route) + "module.exports = {};\n"
    return _js_banner("sources.js", lang, route) + (
        "const {buildSource} = require('libs/dataset/v2');\n\n"
        "module.exports = {\n"
        "  rows: buildSource({\n"
        "    datasetId: Editor.getId('dataset'),\n"
        f"    columns: {json.dumps(aliases, ensure_ascii=False)},\n"
        "  }),\n"
        "};\n"
    )


def _sql_expression(alias: str) -> str:
    text = {
        "bucket": "toStartOfDay(event_time)",
        "current_value": "sum(metric_value)",
        "comparator_value": "sum(comparison_value)",
        "value": "sum(metric_value)",
        "increment": "sum(metric_value)",
        "label": "category_name",
        "group": "series_name",
        "target": "sum(target_value)",
        "source": "source_name",
        "x": "avg(x_value)",
        "y": "avg(y_value)",
        "size": "sum(size_value)",
        "min": "min(metric_value)",
        "q1": "quantile(0.25)(metric_value)",
        "median": "quantile(0.5)(metric_value)",
        "q3": "quantile(0.75)(metric_value)",
        "max": "max(metric_value)",
        "entity_id": "entity_id",
        "entity_name": "entity_name",
        "item": "item_name",
        "status": "status_key",
        "owner": "owner_name",
        "updated_at": "max(updated_at)",
        "amount": "sum(amount)",
        "details_url": "details_url",
        "category": "category_name",
        "completed": "sum(completed_value)",
        "total": "sum(total_value)",
        "metric": "metric_name",
        "series_type": "series_type",
        "series_role": "series_role",
        "title": "option_title",
    }.get(alias)
    if alias == "target" and text is None:
        text = "target_name"
    return text or alias


def _clickhouse_source(aliases: list[str], lang: str, route: str) -> str:
    if not aliases:
        return _js_banner("sources.js", lang, route) + "module.exports = {};\n"
    select = ",\n    ".join(f"{_sql_expression(alias)} AS {alias}" for alias in aliases)
    groupable = [
        alias
        for alias in aliases
        if alias
        in {
            "bucket",
            "label",
            "group",
            "source",
            "target",
            "entity_id",
            "entity_name",
            "item",
            "status",
            "owner",
            "details_url",
            "category",
            "metric",
            "series_type",
            "series_role",
            "title",
        }
    ]
    group_clause = ", ".join(groupable)
    group_sql = f"\n  GROUP BY {group_clause}" if group_clause else ""
    note = (
        "Параметризованный ClickHouse-шаблон с фильтрацией и предварительной агрегацией."
        if lang == "ru"
        else "Parameterized ClickHouse template with filtering and pre-aggregation."
    )
    sql_note = (
        "замените __TABLE__ и универсальные имена исходных полей" if lang == "ru" else "replace __TABLE__ and the generic source columns"
    )
    return (
        _js_banner("sources.js", lang, route)
        + f"""// {note}
const params = Editor.getParams ? (Editor.getParams() || {{}}) : {{}};
function sqlLiteral(value) {{
  return "'" + String(value == null ? '' : value).split("'").join("''") + "'";
}}
const dateFrom = sqlLiteral((params.dateFrom || ['2026-01-01'])[0]);
const dateTo = sqlLiteral((params.dateTo || ['2026-01-30'])[0]);
const allowedSteps = new Set(['auto', 'day', 'week', 'month']);
const requestedStep = String((params.timeStep || ['auto'])[0]);
const timeStep = allowedSteps.has(requestedStep) ? requestedStep : 'auto';
const sqlQuery = `
  SELECT
    {select}
  FROM __TABLE__
  WHERE event_date BETWEEN toDate(${{dateFrom}}) AND toDate(${{dateTo}}){group_sql}
  ORDER BY 1
  /* timeStep=${{timeStep}}; {sql_note} */
`;
module.exports = {{
  rows: {{qlConnectionId: Editor.getId('defaultConnection'), data: {{sql_query: sqlQuery}}}},
}};
"""
    )


def compile_case(
    catalog: dict[str, Any],
    case: dict[str, Any],
    compiled_recipes: dict[tuple[str, str], dict[str, Any]],
) -> dict[str, Any]:
    defaults = _case_defaults(case)
    objects: list[dict[str, Any]] = []
    recipe_by_slug = {item["slug"]: item for item in catalog["recipes"]}
    for item in case["objects"]:
        object_id = str(item["id"])
        route = str(item["route"])
        recipe_slug = str(item.get("recipe") or "")
        localized: dict[str, Any] = {}
        for lang in LOCALES:
            if recipe_slug:
                compiled = compiled_recipes[(recipe_slug, lang)]
                source_contract = compiled["source_contract"]
                aliases = [field["alias"] for field in source_contract]
                shared_tabs = dict(compiled["tabs"])
            else:
                source_contract = []
                aliases = []
                shared_tabs = {
                    "meta.json": "{}\n",
                    "params.js": "",
                    "sources.js": "",
                    "controls.js": _case_controls_js(str(case["kind"]), lang, route),
                }
            params = {**defaults, "theme": ["light"]}
            shared_tabs["params.js"] = _params_js(params, lang, route)
            modes: dict[str, dict[str, str]] = {}
            for mode in catalog["source_modes"]:
                tabs = dict(shared_tabs)
                tabs["meta.json"] = _case_meta(mode, catalog)
                tabs["sources.js"] = (
                    _dataset_source(aliases, lang, route) if mode == "dataset" else _clickhouse_source(aliases, lang, route)
                )
                modes[mode] = {name: tabs[name] for name in EXPECTED_TABS[route]}
            localized[lang] = {
                "title": _case_object_title(item, lang),
                "source_contract": source_contract,
                "modes": modes,
            }
        objects.append(
            {
                "id": object_id,
                "route": route,
                "role": str(item["role"]),
                "recipe": recipe_slug,
                "localized": localized,
            }
        )
    return {
        "slug": str(case["slug"]),
        "kind": str(case["kind"]),
        "title": dict(case["title"]),
        "summary": dict(case["summary"]),
        "params": list(case["params"]),
        "objects": objects,
        "source_modes": list(catalog["source_modes"]),
    }


def _case_object_title(item: dict[str, Any], lang: str) -> str:
    labels = {
        "ru": {
            "controls": "Селекторы",
            "kpi": "KPI",
            "trend": "Тренд",
            "summary": "Сводный график",
            "detail": "Детальная таблица",
            "heatmap": "Heatmap",
            "status_table": "Таблица состояний",
        },
        "en": {
            "controls": "Selectors",
            "kpi": "KPI",
            "trend": "Trend",
            "summary": "Summary chart",
            "detail": "Detail table",
            "heatmap": "Heatmap",
            "status_table": "Status table",
        },
    }
    return labels[lang].get(str(item["role"]), str(item["id"]))


def build_expected_files() -> dict[str, str]:
    catalog = load_catalog()
    compiled_map: dict[tuple[str, str], dict[str, Any]] = {}
    for recipe in catalog["recipes"]:
        for lang in LOCALES:
            compiled_map[(recipe["slug"], lang)] = compile_recipe(catalog, recipe, lang)
    compiled_cases = [compile_case(catalog, case, compiled_map) for case in catalog["cases"]]
    expected: dict[str, str] = {}
    for recipe in catalog["recipes"]:
        slug = str(recipe["slug"])
        localized = {lang: compiled_map[(slug, lang)] for lang in LOCALES}
        for lang, compiled in localized.items():
            prefix = f"recipes/{slug}/code/{lang}"
            for name, content in compiled["tabs"].items():
                expected[f"{prefix}/{name}"] = content if content.endswith("\n") else content + "\n"
            for name, content in compiled["support_files"].items():
                expected[f"{prefix}/{name}"] = content
        expected[f"recipes/{slug}/preview.svg"] = render_svg_preview(localized["ru"], "ru")
        expected[f"recipes/{slug}/preview_en.svg"] = render_svg_preview(localized["en"], "en")
        expected[f"recipes/{slug}/README.md"] = render_recipe_markdown(localized["ru"], "ru", catalog["pages_url"])
        expected[f"recipes/{slug}/README_en.md"] = render_recipe_markdown(localized["en"], "en", catalog["pages_url"])
        payload = _recipe_page_payload(catalog, localized)
        expected[f"recipes/{slug}/index.html"] = render_html(payload, base="../../")
    for compiled_case in compiled_cases:
        slug = compiled_case["slug"]
        for obj in compiled_case["objects"]:
            for lang in LOCALES:
                for mode in compiled_case["source_modes"]:
                    prefix = f"cases/{slug}/objects/{obj['id']}/{mode}/code/{lang}"
                    for name, content in obj["localized"][lang]["modes"][mode].items():
                        expected[f"{prefix}/{name}"] = content if content.endswith("\n") else content + "\n"
        expected[f"cases/{slug}/README.md"] = render_case_markdown(compiled_case, "ru", catalog["pages_url"])
        expected[f"cases/{slug}/README_en.md"] = render_case_markdown(compiled_case, "en", catalog["pages_url"])
        expected[f"cases/{slug}/preview.svg"] = render_case_svg(compiled_case, "ru")
        expected[f"cases/{slug}/preview_en.svg"] = render_case_svg(compiled_case, "en")
        expected[f"cases/{slug}/index.html"] = render_html(_case_page_payload(catalog, compiled_case), base="../../")
    index_payload = _index_payload(catalog)
    expected["index.html"] = render_html({**index_payload, "page_type": "tips"}, base="./")
    expected["visualizations/index.html"] = render_html({**index_payload, "page_type": "library"}, base="../")
    expected["cases/index.html"] = render_html({**index_payload, "page_type": "cases_index"}, base="../")
    expected["README.md"] = render_index_markdown(catalog, "ru")
    expected["README_en.md"] = render_index_markdown(catalog, "en")
    manifest = build_manifest(catalog, compiled_map, compiled_cases, expected)
    expected["manifest.json"] = pretty_json(manifest)
    return expected


def _index_payload(catalog: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_id": SCHEMA_ID,
        "viewports": catalog["viewports"],
        "tips": catalog["tips"],
        "recipes": [
            {key: item[key] for key in ("slug", "variant", "family", "route", "group", "title", "summary")} for item in catalog["recipes"]
        ],
        "cases": [{key: item[key] for key in ("slug", "kind", "title", "summary")} for item in catalog["cases"]],
    }


def _recipe_page_payload(catalog: dict[str, Any], localized: dict[str, dict[str, Any]]) -> dict[str, Any]:
    base = _index_payload(catalog)
    return {**base, "page_type": "recipe", "recipe": {lang: _public_recipe_payload(value) for lang, value in localized.items()}}


def _public_recipe_payload(recipe: dict[str, Any]) -> dict[str, Any]:
    return {
        key: recipe[key]
        for key in (
            "slug",
            "variant",
            "family",
            "route",
            "group",
            "lang",
            "title",
            "summary",
            "use_case",
            "behavior",
            "tooltip",
            "tab_order",
            "tabs",
            "support_files",
            "source_contract",
            "fixture_rows",
            "params",
        )
    }


def _case_page_payload(catalog: dict[str, Any], compiled_case: dict[str, Any]) -> dict[str, Any]:
    return {**_index_payload(catalog), "page_type": "case", "case": compiled_case, "viewports": catalog["viewports"]}


def render_html(payload: dict[str, Any], *, base: str) -> str:
    styles = STYLE_SOURCE.read_text(encoding="utf-8")
    app = APP_SOURCE.read_text(encoding="utf-8").replace("</script>", "<\\/script>")
    encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    encoded = encoded.replace("</script>", "<\\/script>").replace("<!--", "<\\!--")
    return f"""<!doctype html>
<html lang="ru">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <meta name="description" content="Copy-ready JavaScript visualization recipes and linked DataLens cases.">
  <title>JavaScript Visualization Cookbook · datalens-dev-mcp</title>
  <style>{styles}</style>
</head>
<body data-base="{html.escape(base)}">
  <header id="topbar"></header>
  <div class="site-shell"><aside id="sidebar"></aside><main id="content" tabindex="-1"></main></div>
  <script id="cookbook-data" type="application/json">{encoded}</script>
  <script>{app}</script>
</body>
</html>
"""


def render_index_markdown(catalog: dict[str, Any], lang: str) -> str:
    en = lang == "en"
    pages_url = catalog["pages_url"]
    lines = [
        "# JavaScript Visualization Cookbook",
        "",
        "[Русский](README.md) · **English**" if en else "**Русский** · [English](README_en.md)",
        "",
        (
            f"[Open the interactive Cookbook →]({pages_url}?lang={lang})"
            if en
            else f"[Открыть интерактивный Cookbook →]({pages_url}?lang={lang})"
        ),
        "",
        (
            "The cookbook starts with shared Tips, then provides 34 standalone recipes and three linked cases."
            if en
            else "Cookbook начинается с общих Tips, затем содержит 34 самостоятельных рецепта и три связанных кейса."
        ),
        "",
        f"- [Tips]({pages_url}?lang={lang})",
        f"- [{'Visualizations' if en else 'Визуализации'}]({pages_url}visualizations/?lang={lang})",
        f"- [{'Cases' if en else 'Кейсы применения'}]({pages_url}cases/?lang={lang})",
        "",
        f"## {'Visualizations' if en else 'Визуализации'}",
        "",
        "| Recipe | Family | Route | SVG |",
        "| --- | --- | --- | --- |",
    ]
    for recipe in catalog["recipes"]:
        readme = "README_en.md" if en else "README.md"
        preview = "preview_en.svg" if en else "preview.svg"
        lines.append(
            f"| [{recipe['title'][lang]}](recipes/{recipe['slug']}/{readme}) | "
            f"`{recipe['family']}` | `{recipe['route']}` | "
            f"[SVG](recipes/{recipe['slug']}/{preview}) |"
        )
    lines.extend(["", f"## {'Cases' if en else 'Кейсы применения'}", ""])
    for case in catalog["cases"]:
        readme = "README_en.md" if en else "README.md"
        lines.append(f"- [{case['title'][lang]}](cases/{case['slug']}/{readme})")
    lines.extend(
        [
            "",
            "```bash",
            "python3 scripts/build_javascript_cookbook.py --write",
            "python3 scripts/build_javascript_cookbook.py --check",
            "```",
            "",
        ]
    )
    return "\n".join(lines)


def render_recipe_markdown(recipe: dict[str, Any], lang: str, pages_url: str) -> str:
    en = lang == "en"
    preview = "preview_en.svg" if en else "preview.svg"
    lines = [
        f"# {recipe['title']}",
        "",
        "[Русский](README.md) · **English**" if en else "**Русский** · [English](README_en.md)",
        "",
        f"[← Cookbook](../../{'README_en.md' if en else 'README.md'}) · [Web]({pages_url}recipes/{recipe['slug']}/?lang={lang})",
        "",
        f"![{recipe['title']}]({preview})",
        "",
        recipe["summary"],
        "",
        f"## {'When to use it' if en else 'Когда использовать'}",
        "",
        recipe["use_case"],
        "",
        f"## {'Specific behavior' if en else 'Особенности поведения'}",
        "",
        recipe["behavior"],
        "",
        f"## {'Sources contract' if en else 'Контракт Sources'}",
        "",
    ]
    if recipe["source_contract"]:
        lines.extend(
            [
                (
                    "| Alias | Purpose | Type / format | Null behavior | Example |"
                    if en
                    else "| Alias | Назначение | Тип / формат | Поведение null | Пример |"
                ),
                "| --- | --- | --- | --- | --- |",
            ]
        )
        for field in recipe["source_contract"]:
            lines.append(
                f"| `{field['alias']}` | {field['meaning']} | `{field['type']}` / "
                f"{field['format']} | {field['null_behavior']} | "
                f"`{json.dumps(field['example'], ensure_ascii=False)}` |"
            )
    else:
        lines.append("No external source is required." if en else "Внешний источник не требуется.")
    lines.extend(["", f"## {'What to change' if en else 'Что менять'}", ""])
    lines.append("1. Replace Meta and Sources only; keep aliases stable." if en else "1. Замените только Meta и Sources, сохранив aliases.")
    lines.append(
        "2. Use the CUSTOMIZE block for optional labels, palette, units, and formatting."
        if en
        else "2. Для необязательных подписей, палитры, единиц и форматов используйте блок CUSTOMIZE."
    )
    lines.extend(["", f"## {'Files' if en else 'Файлы'}", ""])
    prefix = f"code/{lang}"
    for name in [*recipe["tab_order"], *recipe["support_files"]]:
        lines.append(f"- [`{name}`]({prefix}/{name})")
    lines.append("")
    return "\n".join(lines)


def render_case_markdown(case: dict[str, Any], lang: str, pages_url: str) -> str:
    en = lang == "en"
    lines = [
        f"# {case['title'][lang]}",
        "",
        "[Русский](README.md) · **English**" if en else "**Русский** · [English](README_en.md)",
        "",
        f"[← Cookbook](../../{'README_en.md' if en else 'README.md'}) · [Web]({pages_url}cases/{case['slug']}/?lang={lang})",
        "",
        case["summary"][lang],
        "",
        f"## {'Parameter map' if en else 'Карта параметров'}",
        "",
        (
            "| Param | Owner | Readers | Type | Default | Purpose |"
            if en
            else "| Параметр | Владелец | Читатели | Тип | Default | Назначение |"
        ),
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for item in case["params"]:
        lines.append(
            f"| `{item['name']}` | `{item['owner']}` | "
            f"`{', '.join(item['readers'])}` | `{item['type']}` | "
            f"`{json.dumps(item['default'])}` | {item['purpose'][lang]} |"
        )
    lines.extend(["", f"## {'Copy order' if en else 'Порядок копирования'}", ""])
    for index, item in enumerate(case["objects"], 1):
        lines.append(f"{index}. `{item['id']}` — `{item['route']}`")
    lines.extend(
        [
            "",
            (
                "Dataset is the default mode; ClickHouse is an explicit pre-aggregated alternative."
                if en
                else "Dataset — основной режим; ClickHouse — отдельная альтернатива с предварительной агрегацией."
            ),
            "",
        ]
    )
    return "\n".join(lines)


def render_svg_preview(recipe: dict[str, Any], lang: str) -> str:
    title = html.escape(recipe["title"])
    family = recipe["family"]
    rows = recipe["fixture_rows"]
    marks: list[str] = []
    if family.startswith("kpi_"):
        value = rows[0].get("current_value", "—") if rows else "—"
        marks.append(
            '<text x="72" y="230" font-family="Arial,sans-serif" '
            'font-size="78" font-weight="800" fill="#111827">'
            f"{html.escape(str(value))}</text>"
        )
    elif family == "heatmap":
        for index, row in enumerate(rows[:6]):
            x = 270 + (index % 3) * 170
            y = 120 + (index // 3) * 95
            marks.append(
                '<rect data-role="heatmap-cell" '
                f'data-x="{html.escape(str(row.get("label")))}" '
                f'data-y="{html.escape(str(row.get("group")))}" '
                f'x="{x}" y="{y}" width="156" height="78" '
                f'fill="#2B75E2" opacity="{0.25 + index * 0.1:.2f}"/>'
            )
    elif family == "sankey_status_flow":
        marks.extend(
            [
                '<rect data-role="sankey-node" x="140" y="130" width="24" height="130" fill="#2B75E2"/>',
                '<path data-role="sankey-link" '
                'd="M164 155 C390 155 470 220 700 220" fill="none" '
                'stroke="#2B75E2" stroke-width="24" opacity=".35"/>',
                '<rect data-role="sankey-node" x="700" y="165" width="24" height="130" fill="#008A91"/>',
            ]
        )
    elif recipe["route"] == "editor_table":
        for index in range(4):
            marks.append(
                f'<rect x="70" y="{120 + index * 58}" width="820" height="52" '
                f'fill="{("#F2F4F7" if index == 0 else "#FFFFFF")}" '
                'stroke="#E4E7EC"/>'
            )
    elif family == "area_completion":
        marks.append(
            '<path data-role="area-fill" '
            'd="M100 350 L100 270 L280 225 L460 250 L640 165 L820 210 L820 350 Z" '
            'fill="#2B75E2" opacity=".18"/>'
            '<polyline points="100,270 280,225 460,250 640,165 820,210" '
            'fill="none" stroke="#2B75E2" stroke-width="5"/>'
        )
    else:
        marks.append(
            '<polyline points="100,310 270,250 440,270 610,180 820,205" '
            'fill="none" stroke="#2B75E2" stroke-width="5"/>'
        )
    note = "Синтетический статический preview" if lang == "ru" else "Synthetic static preview"
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="960" height="480" viewBox="0 0 960 480">
<rect width="960" height="480" fill="#F4F6F9"/><rect x="28" y="28" width="904" height="424" rx="18" fill="#FFF" stroke="#E4E7EC"/>
<text x="56" y="72" font-family="Arial,sans-serif" font-size="14" font-weight="700" fill="#667085">{html.escape(note)} · {title}</text>
{''.join(marks)}
</svg>
"""


def render_case_svg(case: dict[str, Any], lang: str) -> str:
    title = html.escape(case["title"][lang])
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="960" height="540" viewBox="0 0 960 540">
<rect width="960" height="540" fill="#F4F6F9"/>
<text x="48" y="60" font-family="Arial" font-size="22" font-weight="800" fill="#111827">{title}</text>
<rect x="48" y="88" width="864" height="70" rx="12" fill="#FFF" stroke="#D0D5DD"/>
<rect x="48" y="180" width="260" height="150" rx="12" fill="#FFF" stroke="#D0D5DD"/>
<rect x="330" y="180" width="582" height="150" rx="12" fill="#FFF" stroke="#D0D5DD"/>
<rect x="48" y="352" width="864" height="140" rx="12" fill="#FFF" stroke="#D0D5DD"/>
</svg>
"""


def build_manifest(
    catalog: dict[str, Any],
    compiled_map: dict[tuple[str, str], dict[str, Any]],
    cases: list[dict[str, Any]],
    expected: dict[str, str],
) -> dict[str, Any]:
    recipe_rows: list[dict[str, Any]] = []
    for recipe in catalog["recipes"]:
        slug = recipe["slug"]
        locales: dict[str, Any] = {}
        canonical_hashes = set()
        for lang in LOCALES:
            compiled = compiled_map[(slug, lang)]
            canonical_hashes.add(compiled["canonical_executable_sha256"])
            prefix = f"recipes/{slug}/code/{lang}"
            paths = [f"{prefix}/{name}" for name in [*compiled["tab_order"], *compiled["support_files"]]]
            locales[lang] = {
                "structure_hashes": compiled["structure_hashes"],
                "files": [{"path": path, "bytes": len(expected[path].encode()), "sha256": sha256_text(expected[path])} for path in paths],
            }
        recipe_rows.append(
            {
                "slug": slug,
                "variant": recipe["variant"],
                "family": recipe["family"],
                "route": recipe["route"],
                "tabs": recipe["tabs"],
                "canonical_executable_hashes": sorted(canonical_hashes),
                "source_aliases": [field_contract(catalog, key, "en")["alias"] for key in recipe["source_columns"]],
                "locales": locales,
            }
        )
    case_rows = [
        {"slug": case["slug"], "kind": case["kind"], "object_count": len(case["objects"]), "source_modes": case["source_modes"]}
        for case in cases
    ]
    return {
        "schema_id": SCHEMA_ID,
        "profile_id": catalog["profile_id"],
        "catalog_sha256": sha256_text(canonical_json(catalog)),
        "recipe_count": len(recipe_rows),
        "advanced_visualization_count": sum(item["route"] == "editor_advanced" for item in recipe_rows),
        "table_recipe_count": sum(item["route"] == "editor_table" for item in recipe_rows),
        "selector_recipe_count": sum(item["route"] == "editor_js_control" for item in recipe_rows),
        "case_count": len(case_rows),
        "recipes": recipe_rows,
        "cases": case_rows,
    }


def write_expected(expected: dict[str, str]) -> None:
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    expected_paths = {OUTPUT_ROOT / relative for relative in expected}
    for path in sorted(OUTPUT_ROOT.rglob("*"), reverse=True):
        if path.is_file() and path not in expected_paths:
            path.unlink()
    for path in sorted(OUTPUT_ROOT.rglob("*"), reverse=True):
        if path.is_dir() and not any(path.iterdir()):
            path.rmdir()
    for relative, content in sorted(expected.items()):
        path = OUTPUT_ROOT / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")


def compare_expected(expected: dict[str, str]) -> list[str]:
    issues: list[str] = []
    expected_paths = {OUTPUT_ROOT / relative for relative in expected}
    existing_paths = {path for path in OUTPUT_ROOT.rglob("*") if path.is_file()} if OUTPUT_ROOT.is_dir() else set()
    for path in sorted(expected_paths - existing_paths):
        issues.append(f"missing: {path.relative_to(ROOT).as_posix()}")
    for path in sorted(existing_paths - expected_paths):
        issues.append(f"unexpected: {path.relative_to(ROOT).as_posix()}")
    for relative, content in sorted(expected.items()):
        path = OUTPUT_ROOT / relative
        if path.is_file() and path.read_text(encoding="utf-8") != content:
            issues.append(f"stale: {path.relative_to(ROOT).as_posix()}")
    return issues


def main() -> int:
    parser = argparse.ArgumentParser(description="Build or check the JavaScript Visualization Cookbook.")
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if not args.write and not args.check:
        parser.error("choose --write, --check, or both")
    try:
        expected = build_expected_files()
    except (KeyError, TypeError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    if args.write:
        write_expected(expected)
    issues = compare_expected(expected) if args.check else []
    if issues:
        print("\n".join(issues), file=sys.stderr)
        return 1
    manifest = json.loads(expected["manifest.json"])
    print(
        json.dumps(
            {
                "ok": True,
                "schema_id": manifest["schema_id"],
                "recipe_count": manifest["recipe_count"],
                "case_count": manifest["case_count"],
                "advanced_visualization_count": manifest["advanced_visualization_count"],
                "table_recipe_count": manifest["table_recipe_count"],
                "selector_recipe_count": manifest["selector_recipe_count"],
                "output": OUTPUT_ROOT.relative_to(ROOT).as_posix(),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
