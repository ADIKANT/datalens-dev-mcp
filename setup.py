"""Stamp built artifacts, without importing the runtime or modifying source files."""
from __future__ import annotations

import json
import runpy
from pathlib import Path

from setuptools import setup
from setuptools.command.build_py import build_py
from setuptools.command.sdist import sdist

ROOT = Path(__file__).resolve().parent
PACKAGE = ROOT / "src/datalens_dev_mcp"
PROVENANCE = runpy.run_path(str(PACKAGE / "provenance.py"))["build_provenance"]


def stamp(directory, value):
    target = Path(directory) / "_build_provenance.json"
    target.write_text(json.dumps(value, sort_keys=True, indent=2) + "\n")


class ProvenanceBuild(build_py):
    def run(self):
        value = PROVENANCE(ROOT)
        super().run()
        stamp(Path(self.build_lib) / "datalens_dev_mcp", value)


class ProvenanceSdist(sdist):
    def make_release_tree(self, base_dir, files):
        value = PROVENANCE(ROOT)
        super().make_release_tree(base_dir, files)
        stamp(Path(base_dir) / "src/datalens_dev_mcp", value)


setup(cmdclass={"build_py": ProvenanceBuild, "sdist": ProvenanceSdist})
