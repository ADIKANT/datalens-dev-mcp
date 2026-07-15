import unittest
from pathlib import Path


REMOVED_ALIASES = {
    "g02_kpi_status_blocked",
    "g05_kpi_no_data",
    "g06_kpi_strip_composite",
    "g13_slope_type_open",
    "g14_bump_priority_rank",
    "g15_streamgraph_status_category",
    "g16_sparkline_created",
    "g18_timeline_created",
    "g19_small_multiple_priority",
    "g23_stacked_bar_status_type",
    "g25_lollipop_epics",
    "g27_dumbbell_type_created_completed",
    "g41_density_age",
    "g43_jitter_priority_age",
    "g44_beeswarm_priority_age",
    "g60_table_standard",
    "g61_table_custom_bars",
    "g62_registry_table",
    "g63_summary_rows_table",
    "g64_status_heat_table",
    "g65_table_sparkline",
}


class ChartTaxonomyTests(unittest.TestCase):
    def test_removed_chart_requests_resolve_to_approved_alternatives(self):
        from datalens_dev_mcp.pipeline.chart_taxonomy import APPROVED_CHARTS, resolve_chart_family

        for alias in REMOVED_ALIASES:
            with self.subTest(alias=alias):
                resolved = resolve_chart_family(alias)
                self.assertIn(resolved.status, {"removed", "manual_review"})
                self.assertIn(resolved.approved_alternative, APPROVED_CHARTS)
                self.assertNotEqual(resolved.approved_alternative, alias)

    def test_family_gallery_contains_only_approved_reachable_families(self):
        from datalens_dev_mcp.editor.bundle import FAMILY_GALLERY
        from datalens_dev_mcp.pipeline.chart_taxonomy import APPROVED_CHARTS, REMOVED_CHARTS

        for family in FAMILY_GALLERY:
            with self.subTest(family=family):
                self.assertIn(family, APPROVED_CHARTS)
                self.assertNotIn(family, REMOVED_CHARTS)

    def test_governance_inference_maps_removed_requests_to_alternatives(self):
        from datalens_dev_mcp.pipeline.governance import infer_family_and_route

        cases = {
            "show a lollipop chart for epics": ("horizontal_bar", "wizard_native"),
            "make a density chart for issue age": ("histogram", "editor_advanced"),
            "need table sparkline details": ("table_node", "wizard_native"),
            "build a bump chart for priority rank": ("horizontal_bar", "wizard_native"),
        }

        for request, expected in cases.items():
            with self.subTest(request=request):
                self.assertEqual(infer_family_and_route(request), expected)

    def test_normal_gallery_examples_do_not_ship_removed_variants(self):
        blocked_terms = [
            "bump_chart",
            "slope_chart",
            "streamgraph",
            "small_multiple",
            "lollipop",
            "dumbbell",
            "density",
            "jitter",
            "beeswarm",
            "kpi_strip",
            "kpi_no_data",
            "cell_bar_encoding",
            "row_sparkline_encoding",
            "cell_bar_and_row_sparkline_encoding",
        ]
        gallery_root = Path("examples/gallery")
        text = "\n".join(
            path.read_text(encoding="utf-8")
            for path in gallery_root.rglob("*")
            if path.is_file()
        )

        for term in blocked_terms:
            with self.subTest(term=term):
                self.assertNotIn(term, text)

    def test_required_taxonomy_documents_exist(self):
        for path in [
            Path("docs/datalens/chart_taxonomy.md"),
            Path("docs/datalens/chart_removal_mapping.md"),
            Path("docs/datalens/chart_selection_decision_matrix.md"),
        ]:
            with self.subTest(path=path):
                self.assertTrue(path.is_file(), f"{path} is missing")


if __name__ == "__main__":
    unittest.main()
