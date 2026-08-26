from __future__ import annotations

import json
from pathlib import Path
from typing import Any


CORPUS_ROOT = Path(__file__).with_name("sessions")


def load_cases() -> list[dict[str, Any]]:
    return [json.loads(path.read_text(encoding="utf-8")) for path in sorted((CORPUS_ROOT / "cases").glob("*.json"))]
