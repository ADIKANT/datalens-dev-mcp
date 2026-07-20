import hashlib
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.run_portable_wheel_smoke import (
    _isolated_subprocess_env,
    _path_is_within,
    _sha256_file,
)


class PortableWheelSmokeTests(unittest.TestCase):
    def test_subprocess_environment_removes_source_import_contamination(self):
        with patch.dict(
            os.environ,
            {
                "PYTHONPATH": "/workspace/src",
                "PYTHONHOME": "/workspace/python",
                "PYTHONSTARTUP": "/workspace/startup.py",
                "PYTHONUSERBASE": "/workspace/userbase",
                "VIRTUAL_ENV": "/workspace/venv",
                "UNRELATED_SETTING": "preserved",
            },
            clear=True,
        ):
            env, removed = _isolated_subprocess_env()

        self.assertEqual(
            removed,
            ["PYTHONHOME", "PYTHONPATH", "PYTHONSTARTUP", "PYTHONUSERBASE", "VIRTUAL_ENV"],
        )
        for key in removed:
            self.assertNotIn(key, env)
        self.assertEqual(env["UNRELATED_SETTING"], "preserved")
        self.assertEqual(env["PYTHONNOUSERSITE"], "1")
        self.assertEqual(env["PYTHONDONTWRITEBYTECODE"], "1")

    def test_wheel_hash_and_import_path_binding_are_deterministic(self):
        with tempfile.TemporaryDirectory() as tmp:
            venv_dir = Path(tmp) / "venv"
            package = venv_dir / "lib" / "python3.12" / "site-packages" / "datalens_dev_mcp"
            package.mkdir(parents=True)
            module_path = package / "__init__.py"
            module_path.write_bytes(b"fixture-wheel-content")
            outside = Path(tmp) / "src" / "datalens_dev_mcp" / "__init__.py"
            outside.parent.mkdir(parents=True)
            outside.write_bytes(b"source-tree-content")

            digest = _sha256_file(module_path)

        self.assertEqual(digest, hashlib.sha256(b"fixture-wheel-content").hexdigest())
        self.assertTrue(_path_is_within(str(module_path), venv_dir))
        self.assertFalse(_path_is_within(str(outside), venv_dir))


if __name__ == "__main__":
    unittest.main()
