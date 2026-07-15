import subprocess
import sys
import unittest


class JavaScriptTemplateValidationTests(unittest.TestCase):
    def test_shipped_javascript_passes_syntax_and_wrapfn_checks(self):
        result = subprocess.run(
            [sys.executable, "scripts/check_js_templates.py"],
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("checked_js_files", result.stdout)
        self.assertIn("wrapfn_files", result.stdout)


if __name__ == "__main__":
    unittest.main()
