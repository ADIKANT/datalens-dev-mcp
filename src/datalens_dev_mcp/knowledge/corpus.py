from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable


CORPUS_RELATIVE_PATH = Path("outputs") / "datalens-docs-corpus"
REPO_CORPUS_ROOT = Path(__file__).resolve().parents[3] / ".external" / "datalens-docs-corpus"
DEFAULT_REQUIRED_FILES = (
    "pages.jsonl",
    "chunks.jsonl",
    "assets.jsonl",
    "manifest.jsonl",
    "api_inventory.json",
    "raw/api/openapi.json",
    "reports/content_hashes.json",
    "reports/validation.md",
)


def normalize_corpus_root(path: str | Path) -> Path:
    expanded = Path(path).expanduser()
    if (expanded / "api_inventory.json").is_file():
        return expanded
    nested = expanded / CORPUS_RELATIVE_PATH
    if (nested / "api_inventory.json").is_file():
        return nested
    return expanded


def corpus_root_candidates(explicit: str | Path | None = None) -> list[Path]:
    # An explicit path is an assertion about the source snapshot. Falling back
    # to a different mirror would turn drift or missing-input checks into false
    # successes.
    if explicit:
        candidates = [Path(explicit)]
    else:
        candidates = []
        env_value = os.getenv("DATALENS_DOCS_CORPUS_ROOT", "").strip()
        if env_value:
            candidates.append(Path(env_value))
        candidates.append(REPO_CORPUS_ROOT)
    resolved: list[Path] = []
    seen: set[Path] = set()
    for candidate in candidates:
        normalized = normalize_corpus_root(candidate)
        if normalized in seen:
            continue
        seen.add(normalized)
        resolved.append(normalized)
    return resolved


def is_corpus_root(path: str | Path, *, required_files: Iterable[str] = DEFAULT_REQUIRED_FILES) -> bool:
    root = normalize_corpus_root(path)
    return all((root / relative).is_file() for relative in required_files)


def resolve_corpus_root(
    explicit: str | Path | None = None,
    *,
    required_files: Iterable[str] = DEFAULT_REQUIRED_FILES,
) -> Path:
    candidates = corpus_root_candidates(explicit)
    for candidate in candidates:
        if is_corpus_root(candidate, required_files=required_files):
            return candidate
    rendered = ", ".join(str(candidate) for candidate in candidates)
    raise FileNotFoundError(
        "DataLens docs corpus mirror is required. Pass --corpus-root or set "
        f"DATALENS_DOCS_CORPUS_ROOT. Checked: {rendered}"
    )


def default_corpus_root() -> Path:
    try:
        return resolve_corpus_root()
    except FileNotFoundError:
        return normalize_corpus_root(REPO_CORPUS_ROOT)


DEFAULT_CORPUS_ROOT = default_corpus_root()
