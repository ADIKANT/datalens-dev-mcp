#!/usr/bin/env python3
from __future__ import annotations

"""Compatibility entrypoint for the canonical Wizard-first route registry.

The pre-v5 implementation duplicated route defaults and could regenerate a
JS-default/map-only matrix. Matrix construction now belongs to
``sync_wizard_first_route_policy.py`` so every caller receives the same policy.
"""

import json
import shutil
from typing import Any

from sync_wizard_first_route_policy import (
    ASSET_ROOT,
    MATRIX_PATH,
    POLICY_PATH,
    _expected_matrix,
    _read,
    _render,
)


def build_matrix() -> dict[str, Any]:
    return _expected_matrix(_read(POLICY_PATH))


def main() -> None:
    matrix = build_matrix()
    MATRIX_PATH.write_text(_render(matrix), encoding="utf-8")
    packaged = ASSET_ROOT / "config" / MATRIX_PATH.name
    packaged.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(MATRIX_PATH, packaged)
    print(
        json.dumps(
            {
                "ok": True,
                "matrix": str(MATRIX_PATH),
                "policy": matrix.get("route_policy_ref"),
                "family_count": len(matrix.get("families") or {}),
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
