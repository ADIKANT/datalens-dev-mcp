from __future__ import annotations

from pathlib import Path

_SRC_PACKAGE = Path(__file__).resolve().parents[1] / "src" / "datalens_dev_mcp"
__path__ = [str(_SRC_PACKAGE)]

_init_file = _SRC_PACKAGE / "__init__.py"
if _init_file.is_file():
    exec(_init_file.read_text(encoding="utf-8"), globals())
