from __future__ import annotations

import importlib.util
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts"


def _load(name: str):
    sys.path.insert(0, str(SCRIPTS))
    try:
        spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        sys.path.pop(0)


def test_full_acceptance_unit_shards_cover_every_unit_test_once() -> None:
    module = _load("run_full_acceptance")
    shards = module.unit_shards()
    flattened = [path for shard in shards for path in shard]
    expected = sorted(path.relative_to(ROOT).as_posix() for path in (ROOT / "tests/unit").glob("test_*.py"))

    assert sorted(flattened) == expected
    assert len(flattened) == len(set(flattened))
    assert all(shard for shard in shards)


def test_archive_manifest_sanitizer_removes_user_paths_and_normalizes_lines(tmp_path: Path) -> None:
    module = _load("sanitize_archive_manifest")
    posix_user_path = "/" + "Users/example/private/report.json"
    rendered = module.sanitize_manifest_text(
        f"source={posix_user_path}  \r\n"
        "other=C:\\Users\\Example\\private\\report.json\r\n"
    )

    assert "/" + "Users/" not in rendered
    assert "\\Users\\" not in rendered
    assert rendered == "source=<SOURCE_ROOT>\nother=<SOURCE_ROOT>\n"


def test_archive_manifest_generation_is_relative_and_deterministic(tmp_path: Path) -> None:
    module = _load("sanitize_archive_manifest")
    (tmp_path / "nested").mkdir()
    (tmp_path / "nested/b.txt").write_text("second", encoding="utf-8")
    (tmp_path / "a.txt").write_text("first", encoding="utf-8")

    first = module.generate_manifest(tmp_path)
    second = module.generate_manifest(tmp_path)

    assert first == second
    assert "a.txt\t5\t" in first
    assert "nested/b.txt\t6\t" in first
    assert str(tmp_path) not in first
