import subprocess
import sys
import unittest
from pathlib import Path


class GoldenRuntimeGalleryTests(unittest.TestCase):
    def test_inventory_classifies_closed_routes_and_families(self):
        from datalens_dev_mcp.pipeline.golden_runtime_gallery import load_golden_inventory

        inventory = load_golden_inventory()
        route_inventory = inventory["route_inventory"]
        supported_routes = {item["route"] for item in route_inventory["supported"]}
        supported_families = {item["family_id"] for item in inventory["supported_family_inventory"]}
        families_by_route = {
            item["route"]: set(item["families"])
            for item in route_inventory["supported"]
        }

        self.assertEqual(
            supported_routes,
            {
                "editor_advanced",
                "editor_table",
                "editor_markdown",
                "editor_js_control",
                "wizard_native",
                "ql_explicit",
            },
        )
        self.assertLessEqual(supported_families, set().union(*families_by_route.values()))
        self.assertEqual(len(supported_families), 39)
        self.assertIn("ql_explicit", supported_families)
        self.assertIn("grouped_sticky_table_exception", {item["route"] for item in route_inventory["reference_only"]})
        self.assertIn("unknown_wizard_visualization", {item["route"] for item in route_inventory["reference_only"]})
        self.assertIn("d3_node", {item["route"] for item in route_inventory["banned"]})
        self.assertIn("ql_delete", {item["route"] for item in route_inventory["banned"]})
        self.assertIn("automatic_ql_selection", {item["route"] for item in route_inventory["banned"]})

    def test_generated_contracts_match_golden_hashes(self):
        from datalens_dev_mcp.pipeline.golden_runtime_gallery import compare_generated_to_golden

        comparison = compare_generated_to_golden()

        self.assertTrue(comparison["ok"], comparison)
        self.assertEqual(comparison["generated_family_count"], 39)
        self.assertEqual(comparison["golden_family_count"], 39)

    def test_contracts_record_unavailable_live_and_browser_proof_honestly(self):
        from datalens_dev_mcp.pipeline.golden_runtime_gallery import load_golden_contracts

        contracts = load_golden_contracts()

        self.assertEqual(contracts["summary"]["validator_failure_count"], 0)
        self.assertEqual(contracts["summary"]["browser_rendered_available_count"], 0)
        self.assertEqual(contracts["summary"]["browser_rendered_unavailable_count"], 39)
        for contract in contracts["contracts"]:
            with self.subTest(family=contract["family_id"]):
                self.assertTrue(contract["source_data_contract"]["contract_id"])
                self.assertTrue(contract["params_contract"]["contract_id"])
                self.assertTrue(contract["generated_payload"]["sha256"])
                self.assertTrue(contract["validators"]["route_payload"]["ok"], contract["validators"]["route_payload"])
                self.assertEqual(contract["saved_readback"]["status"], "unavailable")
                self.assertEqual(contract["published_readback"]["status"], "unavailable")
                self.assertTrue(contract["saved_readback"]["must_not_claim_passed"])
                self.assertTrue(contract["published_readback"]["must_not_claim_passed"])
                self.assertEqual(contract["browser_proof"]["browser_rendered"], "unavailable")
                self.assertIsNone(contract["browser_proof"]["screenshot_path"])
                self.assertTrue(contract["browser_proof"]["must_not_claim_passed"])

    def test_contracts_stay_parameterized_and_avoid_production_targets(self):
        from datalens_dev_mcp.pipeline.golden_runtime_gallery import (
            STATIC_WORKBOOK_PLACEHOLDER,
            load_golden_contracts,
        )

        contracts = load_golden_contracts()
        refused = set(contracts["write_policy"]["refused_workbook_ids"]["production"])

        for contract in contracts["contracts"]:
            with self.subTest(family=contract["family_id"]):
                self.assertEqual(contract["generated_payload"]["workbook_id"], STATIC_WORKBOOK_PLACEHOLDER)
                self.assertIsNone(contract["saved_readback"]["object_id"])
                self.assertIsNone(contract["published_readback"]["object_id"])
                self.assertTrue(refused.isdisjoint({contract["generated_payload"]["workbook_id"]}))

    def test_gallery_builder_check_script_passes(self):
        root = Path(__file__).resolve().parents[2]
        result = subprocess.run(
            [sys.executable, str(root / "scripts" / "build_golden_runtime_gallery.py"), "--check"],
            cwd=root,
            text=True,
            capture_output=True,
            timeout=30,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
