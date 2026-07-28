from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[2]
TOOLTIP_TEMPLATE = ROOT / "templates" / "advanced" / "tooltip.js"


class TooltipTemplateContractTests(unittest.TestCase):
    def test_single_period_mode_removes_comparison_chrome_and_deduplicates_rows(self):
        html = self._render(
            {
                "title": "Processed period",
                "rows": [
                    {"role": "current", "label": "CURRENT", "value": "42"},
                    {"role": "vs", "label": "VS", "value": ""},
                    {
                        "role": "comparison_period",
                        "label": "Comparison period",
                        "value": "",
                    },
                    {
                        "role": "selected_period",
                        "label": "Period",
                        "value": "01–31 Jul",
                    },
                    {
                        "role": "selected_period",
                        "label": "Period",
                        "value": "01–31 Jul",
                    },
                ],
            }
        )

        self.assertIn('data-tooltip-comparison-mode="single_period"', html)
        self.assertIn('data-tooltip-period-source="normalized"', html)
        self.assertNotIn("CURRENT", html)
        self.assertNotIn(">VS<", html)
        self.assertNotIn("Comparison period", html)
        self.assertEqual(html.count("01–31 Jul"), 1)
        self.assertIn(">42<", html)

    def test_comparison_mode_keeps_complete_context_and_rejects_raw_period_source(self):
        html = self._render(
            {
                "title": "Comparison",
                "comparisonMode": "comparison",
                "rows": [
                    {"role": "current", "label": "CURRENT", "value": "42"},
                    {"role": "vs", "label": "VS", "value": "40"},
                    {
                        "role": "comparison_period",
                        "label": "Comparison period",
                        "value": "01–30 Jun",
                    },
                ],
            }
        )

        self.assertIn('data-tooltip-comparison-mode="comparison"', html)
        self.assertIn("CURRENT", html)
        self.assertIn(">VS<", html)
        self.assertIn("01–30 Jun", html)
        with self.assertRaisesRegex(AssertionError, "periodValueSource"):
            self._render(
                {
                    "title": "Invalid",
                    "periodValueSource": "raw",
                    "rows": [],
                }
            )

    def _render(self, payload: dict[str, object]) -> str:
        node = shutil.which("node")
        if node is None:
            raise unittest.SkipTest("node is required for tooltip template tests")
        script = (
            "const t=require(process.argv[1]);"
            "const p=JSON.parse(process.argv[2]);"
            "process.stdout.write(t.renderTooltipShell(p));"
        )
        completed = subprocess.run(
            [node, "-e", script, str(TOOLTIP_TEMPLATE), json.dumps(payload)],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
        if completed.returncode != 0:
            raise AssertionError(completed.stderr)
        return completed.stdout


if __name__ == "__main__":
    unittest.main()
