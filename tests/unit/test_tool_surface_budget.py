import json
import unittest


class ToolSurfaceBudgetTests(unittest.TestCase):
    def test_standard_tool_surface_stays_bounded_and_policy_driven(self):
        from datalens_dev_mcp.server import STANDARD_TOOL_NAMES, list_tools

        tools = list_tools()
        all_tools = list_tools("all")
        names = {tool["name"] for tool in tools}
        payload_chars = len(json.dumps({"tools": tools}, ensure_ascii=False, separators=(",", ":")))
        all_payload_chars = len(json.dumps({"tools": all_tools}, ensure_ascii=False, separators=(",", ":")))

        self.assertEqual(names, STANDARD_TOOL_NAMES)
        self.assertEqual(len(names), 38)
        self.assertLessEqual(len(names), 40)
        self.assertLessEqual(payload_chars, 34_000)
        self.assertLessEqual(all_payload_chars, 65_000)
        self.assertIn("dl_reference", names)
        self.assertNotIn("dl_rpc_expert", names)
        self.assertNotIn("dl_get_dataset", names)

        reference_tool = next(tool for tool in tools if tool["name"] == "dl_reference")
        reference_modes = set(reference_tool["inputSchema"]["properties"]["mode"]["enum"])
        for mode in (
            "chart_selection",
            "renderer_contract",
            "negative_requirements",
            "delivery_intent",
            "api_contract",
            "current_docs_delta",
            "tool_selection",
        ):
            self.assertIn(mode, reference_modes)


if __name__ == "__main__":
    unittest.main()
