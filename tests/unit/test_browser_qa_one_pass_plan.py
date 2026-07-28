from __future__ import annotations

from copy import deepcopy
import json
import shutil
import subprocess
import unittest

from datalens_dev_mcp.pipeline.browser_qa import (
    BROWSER_QA_ASSERTIONS,
    BROWSER_QA_FORBIDDEN_SOURCE_TOKENS,
    build_browser_qa_plan,
    browser_qa_plan_sha256,
    validate_browser_qa_plan,
)


def _plan():
    return build_browser_qa_plan(
        dashboard_url="https://example.test/dashboards/dashboard-alpha",
        dashboard_id="dashboard-alpha",
        tab_ids=["tab-two", "tab-one"],
        expected_object_ids=["chart-two", "chart-one", "kpi-one"],
        selector_contracts=[
            {
                "selector_id": "selector-period",
                "label": "Period",
                "family": "date_range_selector",
            },
            {"selector_id": "selector-status", "label": "Status"},
        ],
        comparison_enabled=True,
        comparison_context_object_ids=[
            "comparison-context-two",
            "comparison-context-one",
            "comparison-context-one",
        ],
        tooltip_comparison_modes={
            "chart-one": "single_period",
            "kpi-one": "comparison",
        },
        render_contract={
            "legend": {"font_size_px": 12, "line_height_px": 16},
            "selector": {"row_height_px": 44},
        },
    )


def _execute_geometry_plan(
    plan: dict,
    *,
    comparison_top: int,
    comparison_left: int,
    include_selector: bool = True,
    selector_height: int = 44,
) -> dict:
    node = shutil.which("node")
    if node is None:
        raise unittest.SkipTest("node is required for browser QA DOM execution")
    config = {
        "comparison_top": comparison_top,
        "comparison_left": comparison_left,
        "include_selector": include_selector,
        "selector_height": selector_height,
    }
    harness = r"""
class FakeNode {
  constructor({tag = "div", id = "", attrs = {}, classes = [], text = "", box, style = {}}) {
    this.tagName = tag.toUpperCase();
    this.id = id;
    this.attrs = {...attrs};
    this.classList = new Set(classes);
    this.textContent = text;
    this.box = {...box};
    this.style = {...style};
    this.parentElement = null;
    this.children = [];
    this.scrollWidth = box.width;
    this.clientWidth = box.width;
  }
  add(child) {
    child.parentElement = this;
    this.children.push(child);
    return child;
  }
  getAttribute(name) {
    if (name === "id") return this.id || null;
    if (name === "class") return Array.from(this.classList).join(" ");
    return Object.prototype.hasOwnProperty.call(this.attrs, name) ? this.attrs[name] : null;
  }
  getBoundingClientRect() {
    return {
      ...this.box,
      right: this.box.left + this.box.width,
      bottom: this.box.top + this.box.height
    };
  }
  descendants() {
    return this.children.flatMap((child) => [child, ...child.descendants()]);
  }
  querySelectorAll(selector) {
    return this.descendants().filter((candidate) => matches(candidate, selector));
  }
  querySelector(selector) {
    return this.querySelectorAll(selector)[0] || null;
  }
  contains(candidate) {
    let current = candidate;
    while (current) {
      if (current === this) return true;
      current = current.parentElement;
    }
    return false;
  }
}
const matchesPart = (candidate, rawPart) => {
  const part = rawPart.trim();
  if (part === "*") return true;
  if (part.startsWith(".")) return candidate.classList.has(part.slice(1));
  const attribute = part.match(/^\[([^=\]]+)(?:="([^"]*)")?\]$/);
  if (attribute) {
    const actual = candidate.getAttribute(attribute[1]);
    return attribute[2] === undefined ? actual !== null : actual === attribute[2];
  }
  return candidate.tagName.toLowerCase() === part.toLowerCase();
};
const matches = (candidate, selector) =>
  selector.split(",").some((part) => matchesPart(candidate, part));
const html = new FakeNode({
  tag: "html",
  box: {left: 0, top: 0, width: 1200, height: 900}
});
const body = html.add(new FakeNode({
  tag: "body",
  text: "Period Previous equal-length period 42",
  box: {left: 0, top: 0, width: 1200, height: 900}
}));
if (__CONFIG__.include_selector) {
  const selector = body.add(new FakeNode({
    id: "selector-period",
    attrs: {
      "data-widget-id": "selector-period",
      "data-role": "selector",
      "data-selector-row": ""
    },
    text: "Period",
    box: {left: 36, top: 100, width: 1128, height: __CONFIG__.selector_height}
  }));
  selector.add(new FakeNode({
    tag: "label",
    text: "Period",
    box: {left: 36, top: 100, width: 120, height: 44},
    style: {textAlign: "left"}
  }));
}
body.add(new FakeNode({
  id: "comparison-context",
  attrs: {
    "data-widget-id": "comparison-context",
    "data-role": "comparison-context"
  },
  text: "Previous equal-length period",
  box: {
    left: __CONFIG__.comparison_left,
    top: __CONFIG__.comparison_top,
    width: __CONFIG__.comparison_left === 36 ? 1128 : 100,
    height: 28
  }
}));
body.add(new FakeNode({
  id: "kpi-one",
  attrs: {
    "data-widget-id": "kpi-one",
    "data-role": "kpi",
    "data-render-contract": "synthetic"
  },
  text: "42",
  box: {left: 36, top: 188, width: 1128, height: 96},
  style: {backgroundColor: "transparent"}
})).add(new FakeNode({
  attrs: {"data-role": "kpi-value"},
  text: "42",
  box: {left: 48, top: 200, width: 120, height: 38}
}));
const allNodes = [html, ...html.descendants()];
const document = {
  querySelectorAll: (selector) => allNodes.filter((candidate) => matches(candidate, selector)),
  querySelector(selector) {
    return this.querySelectorAll(selector)[0] || null;
  }
};
const defaultStyle = {
  display: "block",
  visibility: "visible",
  opacity: "1",
  borderTopWidth: "0px",
  borderRightWidth: "0px",
  borderBottomWidth: "0px",
  borderLeftWidth: "0px",
  borderRadius: "0px",
  outlineStyle: "none",
  outlineWidth: "0px",
  boxShadow: "none",
  backgroundColor: "transparent",
  fontSize: "12px",
  lineHeight: "16px",
  textAlign: "left",
  overflowY: "visible",
  scrollbarGutter: "auto"
};
const window = {
  innerWidth: 1200,
  innerHeight: 900,
  getComputedStyle: (candidate) => ({...defaultStyle, ...candidate.style})
};
html.scrollWidth = 1200;
html.clientWidth = 1200;
"""
    script = (
        harness.replace("__CONFIG__", json.dumps(config, separators=(",", ":")))
        + "\nconst result = "
        + plan["evaluate"]["source"]
        + ";\nprocess.stdout.write(JSON.stringify(result));\n"
    )
    completed = subprocess.run(
        [node, "-e", script],
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )
    if completed.returncode != 0:
        raise AssertionError(completed.stderr)
    return json.loads(completed.stdout)


class BrowserQaOnePassPlanTests(unittest.TestCase):
    def test_plan_is_deterministic_and_uses_two_viewports_with_three_calls(self):
        first = _plan()
        second = _plan()

        self.assertEqual(first, second)
        self.assertEqual(first["canonical_sha256"], browser_qa_plan_sha256(first))
        self.assertEqual(
            [(item["width"], item["height"]) for item in first["viewports"]],
            [(1200, 900), (1440, 900)],
        )
        self.assertEqual(first["execution"]["max_browser_calls"], 3)
        self.assertEqual(len(first["execution"]["calls"]), 3)
        self.assertEqual(first["execution"]["navigation_count"], 1)
        self.assertEqual(first["execution"]["evaluation_count_per_viewport"], 1)
        self.assertEqual(first["execution"]["screenshots_per_viewport"], 1)
        self.assertEqual(first["execution"]["reload_count"], 0)
        self.assertEqual(first["execution"]["retry_count"], 0)
        self.assertFalse(first["execution"]["dom_mutation_allowed"])
        self.assertTrue(validate_browser_qa_plan(first)["ok"])

    def test_evaluate_source_is_read_only_and_covers_every_required_assertion(self):
        plan = _plan()
        source = plan["evaluate"]["source"]
        lowered = source.lower()

        self.assertIn("querySelector", source)
        self.assertIn("getComputedStyle", source)
        self.assertIn("getBoundingClientRect", source)
        for token in BROWSER_QA_FORBIDDEN_SOURCE_TOKENS:
            self.assertNotIn(token, lowered)

        expected_ids = {item["id"] for item in BROWSER_QA_ASSERTIONS}
        planned_ids = {item["id"] for item in plan["evaluate"]["assertions"]}
        result_ids = set(plan["expected_result"]["assertion_ids"])
        self.assertEqual(planned_ids, expected_ids)
        self.assertEqual(result_ids, expected_ids)
        for assertion_id in expected_ids:
            self.assertIn(assertion_id, source)

        self.assertEqual(plan["render_contract"]["kpi"]["border"], "none")
        self.assertEqual(plan["render_contract"]["kpi"]["border_radius_px"], 0)
        self.assertEqual(plan["render_contract"]["kpi"]["value_marker"], "kpi-value")
        self.assertEqual(plan["render_contract"]["kpi"]["min_height_px"], 88)
        self.assertEqual(plan["render_contract"]["kpi"]["max_height_px"], 112)
        self.assertEqual(plan["render_contract"]["legend"]["font_size_px"], 12)
        self.assertEqual(plan["render_contract"]["legend"]["line_height_px"], 16)
        self.assertEqual(plan["render_contract"]["selector"]["row_height_px"], 44)
        self.assertEqual(plan["render_contract"]["selector"]["row_width"], "bounded")
        self.assertEqual(plan["render_contract"]["selector"]["max_row_width_percent"], 94)
        self.assertTrue(plan["render_contract"]["selector"]["period_first_if_present"])
        self.assertTrue(plan["render_contract"]["selector"]["single_row"])
        self.assertEqual(
            plan["render_contract"]["selector"]["row_target_width_percent"],
            95,
        )
        self.assertTrue(plan["render_contract"]["tooltip"]["single_owner"])
        self.assertEqual(plan["render_contract"]["tooltip"]["border"], "none")
        self.assertEqual(plan["render_contract"]["tooltip"]["border_radius_px"], 0)
        self.assertEqual(plan["render_contract"]["tooltip"]["outline"], "none")
        self.assertEqual(plan["render_contract"]["tooltip"]["shadow"], "none")
        self.assertEqual(
            plan["render_contract"]["tooltip"]["period_value_source"],
            "normalized",
        )
        self.assertEqual(
            plan["tooltip_comparison_modes"],
            {"chart-one": "single_period", "kpi-one": "comparison"},
        )
        self.assertEqual(
            [item["selector_id"] for item in plan["selector_contracts"]],
            ["selector-period", "selector-status"],
        )
        self.assertEqual(plan["selector_contracts"][0]["role"], "period")
        self.assertEqual(
            plan["comparison_context_object_ids"],
            ["comparison-context-one", "comparison-context-two"],
        )
        self.assertFalse(plan["render_contract"]["horizontal_rank"]["scroll"])
        self.assertFalse(plan["render_contract"]["horizontal_rank"]["stable_scrollbar_gutter"])
        self.assertEqual(plan["render_contract"]["horizontal_rank"]["scroll_object_ids"], [])
        self.assertIn("widthPercent <= input.render_contract.selector.max_row_width_percent", source)
        self.assertIn("tooltipShells.length === 1 && tooltipOwners.length === 1", source)
        self.assertIn("tooltip_comparison_mode_contract: tooltipComparisonModeMatches", source)
        self.assertIn("row.actual_mode === row.expected_mode", source)
        self.assertIn("!singlePeriodHasComparisonChrome", source)
        self.assertIn("const useExactComparisonContextIds = input.comparison_context_object_ids.length > 0", source)
        self.assertIn("const node = findObject(objectId)", source)
        self.assertIn("visibleNonemptyComparisonCount === 1", source)
        self.assertIn("visibleNonemptyComparisonCount === 0", source)
        self.assertIn("comparison_context_placement: comparisonPlacementMatches", source)
        self.assertIn("placementTolerancePx = 12", source)
        self.assertIn("placementSelectorNodes.length > 0", source)
        self.assertIn('useExactComparisonContextIds ? "exact_object_ids" : "dom_class_fallback"', source)
        self.assertIn("row.border_none && row.radius_px === 0", source)
        self.assertIn("row.value_marker_found && row.value_visible && row.value_nonempty", source)
        self.assertIn("selector_order_row_contract: selectorOrderMatches", source)
        self.assertIn('all(\'[data-component="horizontal_rank"]\', scope.node)', source)
        self.assertIn('[component, ...all("*", component)]', source)
        self.assertIn("const stableGutterMatches = !stableGutterRequired ||", source)
        self.assertEqual(
            source.count("Math.abs(row.height_px - expectedSelector.row_height_px)"),
            1,
        )
        self.assertEqual(len(plan["artifacts"]["viewports"]), 2)

    def test_readable_legend_uses_active_profile_typography(self):
        plan = build_browser_qa_plan(
            dashboard_id="dashboard-readable-legend",
            tab_ids=["tab-main"],
            expected_object_ids=["chart-main"],
            render_contract={
                "effective_tokens": {
                    "typography": {
                        "legend": {
                            "active_token": "legend.readable",
                            "active": {
                                "font_size_px": 14,
                                "line_height_px": 18,
                            },
                        }
                    }
                }
            },
        )

        self.assertEqual(
            plan["render_contract"]["legend"],
            {
                "font_size_px": 14,
                "line_height_px": 18,
                "maximum_typography_set_size": 1,
            },
        )
        self.assertIn(
            "value === `${expectedLegend.font_size_px}/${expectedLegend.line_height_px}`",
            plan["evaluate"]["source"],
        )
        self.assertTrue(validate_browser_qa_plan(plan)["ok"])

    def test_comparison_context_geometry_executes_against_dom_rects(self):
        def geometry_plan(*, include_selector: bool = True) -> dict:
            return build_browser_qa_plan(
                dashboard_id="dashboard-comparison-geometry",
                tab_ids=["tab-main"],
                expected_object_ids=(
                    ["selector-period", "comparison-context", "kpi-one"]
                    if include_selector
                    else ["comparison-context", "kpi-one"]
                ),
                selector_contracts=(
                    [
                        {
                            "selector_id": "selector-period",
                            "label": "Period",
                            "family": "date_range_selector",
                        }
                    ]
                    if include_selector
                    else []
                ),
                comparison_enabled=True,
                comparison_context_object_ids=["comparison-context"],
            )

        correct = _execute_geometry_plan(
            geometry_plan(),
            comparison_top=152,
            comparison_left=36,
        )
        above = _execute_geometry_plan(
            geometry_plan(),
            comparison_top=64,
            comparison_left=36,
        )
        beside = _execute_geometry_plan(
            geometry_plan(),
            comparison_top=100,
            comparison_left=1064,
        )
        tall_selector = _execute_geometry_plan(
            geometry_plan(),
            comparison_top=178,
            comparison_left=36,
            selector_height=70,
        )
        no_selector = _execute_geometry_plan(
            geometry_plan(include_selector=False),
            comparison_top=152,
            comparison_left=36,
            include_selector=False,
        )

        self.assertTrue(correct["passed"], correct)
        self.assertTrue(correct["assertions"]["comparison_context_placement"])
        self.assertTrue(correct["assertions"]["selector_order_row_contract"])
        self.assertEqual(
            correct["observations"]["comparison_context_placement"][
                "selector_to_context_gap_px"
            ],
            8,
        )
        for misplaced in (above, beside, no_selector):
            self.assertFalse(misplaced["passed"], misplaced)
            self.assertFalse(
                misplaced["assertions"]["comparison_context_placement"],
                misplaced,
            )
        self.assertFalse(tall_selector["passed"], tall_selector)
        self.assertFalse(
            tall_selector["assertions"]["selector_order_row_contract"],
            tall_selector,
        )

    def test_stable_gutter_is_required_only_for_registered_scroll_adapter(self):
        plan = build_browser_qa_plan(
            dashboard_id="dashboard-scroll",
            tab_ids=["tab-main"],
            expected_object_ids=["ranking-scroll"],
            render_contract={
                "effective_tokens": {
                    "horizontal_rank": {
                        "scroll": True,
                        "stable_scrollbar_gutter": True,
                        "scroll_object_ids": [
                            "ranking-scroll",
                            "ranking-scroll",
                        ],
                    }
                }
            },
        )

        horizontal = plan["render_contract"]["horizontal_rank"]
        source = plan["evaluate"]["source"]
        self.assertTrue(horizontal["scroll"])
        self.assertTrue(horizontal["stable_scrollbar_gutter"])
        self.assertEqual(horizontal["scroll_object_ids"], ["ranking-scroll"])
        self.assertIn("horizontalContract.scroll === true", source)
        self.assertIn("horizontalContract.stable_scrollbar_gutter === true", source)
        self.assertIn('[component, ...all("*", component)]', source)
        self.assertIn('css.overflowY === "auto" || css.overflowY === "scroll"', source)
        self.assertIn('String(computed(node).scrollbarGutter)', source)
        self.assertTrue(validate_browser_qa_plan(plan)["ok"])

    def test_comparison_context_ids_are_sorted_unique_and_hash_bound(self):
        plan = _plan()
        self.assertEqual(
            plan["comparison_context_object_ids"],
            ["comparison-context-one", "comparison-context-two"],
        )
        self.assertIn(
            '"comparison_context_object_ids":["comparison-context-one","comparison-context-two"]',
            plan["evaluate"]["source"],
        )

        drift = deepcopy(plan)
        drift["comparison_context_object_ids"] = [
            "comparison-context-two",
            "comparison-context-one",
            "comparison-context-one",
        ]
        drift["canonical_sha256"] = browser_qa_plan_sha256(drift)
        validation = validate_browser_qa_plan(drift)
        self.assertFalse(validation["ok"])
        self.assertIn("comparison_context_object_ids_not_sorted_unique", validation["issues"])

        selector_drift = deepcopy(plan)
        selector_drift["selector_contracts"] = list(
            reversed(selector_drift["selector_contracts"])
        )
        for index, item in enumerate(selector_drift["selector_contracts"]):
            item["ordinal"] = index
        selector_drift["canonical_sha256"] = browser_qa_plan_sha256(
            selector_drift
        )
        selector_validation = validate_browser_qa_plan(selector_drift)
        self.assertFalse(selector_validation["ok"])
        self.assertIn(
            "selector_contracts_not_bound_to_evaluate_source",
            selector_validation["issues"],
        )

    def test_comparison_context_class_fallback_is_used_only_without_exact_ids(self):
        plan = build_browser_qa_plan(
            dashboard_id="dashboard-no-comparison",
            tab_ids=["tab-main"],
            expected_object_ids=["chart-main"],
            comparison_enabled=False,
        )

        self.assertEqual(plan["comparison_context_object_ids"], [])
        source = plan["evaluate"]["source"]
        self.assertIn("const fallbackComparisonContexts = useExactComparisonContextIds", source)
        self.assertIn("? []", source)
        self.assertIn(": all('[data-role=\"comparison-context\"]", source)
        self.assertTrue(validate_browser_qa_plan(plan)["ok"])

    def test_validator_rejects_mutation_and_call_budget_drift(self):
        call_drift = deepcopy(_plan())
        call_drift["execution"]["max_browser_calls"] = 4
        call_drift["execution"]["calls"].append({"ordinal": 4, "operation": "evaluate_again"})
        call_validation = validate_browser_qa_plan(call_drift)
        self.assertFalse(call_validation["ok"])
        self.assertIn("browser_call_budget_exceeded", call_validation["issues"])

        mutation = deepcopy(_plan())
        mutation["evaluate"]["source"] += "\ndocument.body.appendChild(node);"
        mutation_validation = validate_browser_qa_plan(mutation)
        self.assertFalse(mutation_validation["ok"])
        self.assertIn("forbidden_evaluate_token:appendchild(", mutation_validation["issues"])

    def test_validator_rejects_missing_viewport_and_assertion(self):
        plan = deepcopy(_plan())
        plan["viewports"].pop()
        plan["evaluate"]["assertions"] = [
            item for item in plan["evaluate"]["assertions"] if item["id"] != "kpi_surface_contract"
        ]

        validation = validate_browser_qa_plan(plan)

        self.assertFalse(validation["ok"])
        self.assertIn("required_viewports_missing_or_changed", validation["issues"])
        self.assertIn("required_assertions_missing", validation["issues"])


if __name__ == "__main__":
    unittest.main()
