from __future__ import annotations

import re
import tarfile
import zipfile
from dataclasses import dataclass
from pathlib import Path

from datalens_dev_mcp.validators.redaction import BEARER_RE, URL_USERINFO_RE, YC_TOKEN_RE


@dataclass(frozen=True)
class ScanResult:
    ok: bool
    issues: list[str]


SECRET_PATTERNS = (
    BEARER_RE,
    YC_TOKEN_RE,
    URL_USERINFO_RE,
    re.compile(r"\b(?:x-api-key|api-key|apikey|authorization|cookie|set-cookie)\s*[:=]\s*[^\s,;]{12,}", re.I),
    re.compile(r"-----BEGIN\s+(?:RSA\s+|EC\s+|OPENSSH\s+)?PRIVATE KEY-----", re.I),
    re.compile(
        r"\b(?:DATALENS_IAM_TOKEN|YC_IAM_TOKEN|PASSWORD|SECRET|TOKEN|API_KEY|APIKEY)=[A-Za-z0-9._~+/=\-]{20,}\b",
    ),
    re.compile(
        r"\b(?:password|secret|token|api[_-]?key|apikey)\s*=\s*['\"]?[A-Za-z0-9_~+/=\-]{20,}(?!\s*\()['\"]?",
        re.I,
    ),
)
PLACEHOLDER_SECRET_MARKERS = (
    "<",
    "example",
    "fixture",
    "fake",
    "dummy",
    "placeholder",
    "file-token",
    "process-token",
    "old-token",
    "new-token",
    "fresh-token",
    "fresh-cli-token",
    "token-secret",
    "must-not-leak",
    "secret-token-value",
)
SKIP_DIRS = {
    ".git",
    ".venv",
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
    ".mypy_cache",
    "materials",
    "dist",
    "build",
    "sdist",
    "wheel_build",
    "wheel_build_1",
    "wheel_build_2",
    "final_dist",
    "final_sdist",
    "final_wheel_build",
    "release_qualification",
    "final_simple",
}
SKIP_FILE_NAMES = {
    "Pasted text.txt",
    "datalens-dev-mcp-codex-prompts.md",
    "datalens-dev-mcp-roadmap.md",
}
TEXT_EXTENSIONS = {
    ".md",
    ".txt",
    ".py",
    ".json",
    ".toml",
    ".yml",
    ".yaml",
    ".js",
    ".css",
    ".html",
    ".sh",
}
ARCHIVE_EXTENSIONS = {".whl", ".zip", ".gz", ".tgz"}
FORBIDDEN_ARCHIVE_MEMBERS = {"datalens_mcp.local.json"}


def _is_placeholder_secret_line(line: str) -> bool:
    lowered = line.lower()
    if re.search(r"\{[A-Za-z_][A-Za-z0-9_]*\}", line):
        return True
    if re.search(r"\b(?:password|secret|token|api[_-]?key|apikey)\s*=\s*[a-z_][a-z0-9_]*\(", lowered):
        return True
    return any(marker in lowered for marker in PLACEHOLDER_SECRET_MARKERS)


def scan_text(text: str, *, source: str = "<memory>") -> ScanResult:
    issues: list[str] = []
    for number, line in enumerate(text.splitlines(), start=1):
        for pattern in SECRET_PATTERNS:
            if pattern.search(line):
                if _is_placeholder_secret_line(line):
                    continue
                issues.append(f"{source}:{number}: token or secret-like value")
                break
    return ScanResult(ok=not issues, issues=issues)


def scan_path(root: str | Path) -> ScanResult:
    root_path = Path(root)
    issues: list[str] = []
    for path in root_path.rglob("*"):
        if not path.is_file():
            continue
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        if path.name in SKIP_FILE_NAMES:
            continue
        if _is_archive(path):
            issues.extend(_scan_archive(path, root=root_path))
            continue
        if path.suffix and path.suffix not in TEXT_EXTENSIONS:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        result = scan_text(text, source=str(path.relative_to(root_path)))
        issues.extend(result.issues)
    return ScanResult(ok=not issues, issues=issues)


def _is_archive(path: Path) -> bool:
    name = path.name.lower()
    return path.suffix.lower() in ARCHIVE_EXTENSIONS or name.endswith((".tar.gz", ".tgz", ".whl"))


def _scan_archive(path: Path, *, root: Path) -> list[str]:
    issues: list[str] = []
    rel = _relative_source(path, root)
    try:
        if path.suffix.lower() in {".whl", ".zip"}:
            with zipfile.ZipFile(path) as archive:
                for name in archive.namelist():
                    issues.extend(_archive_member_issues(rel, name))
                    if Path(name).suffix.lower() not in TEXT_EXTENSIONS:
                        continue
                    try:
                        text = archive.read(name).decode("utf-8", errors="replace")
                    except Exception:  # noqa: BLE001
                        continue
                    issues.extend(scan_text(text, source=f"{rel}:{name}").issues)
        elif tarfile.is_tarfile(path):
            with tarfile.open(path) as archive:
                for member in archive.getmembers():
                    if not member.isfile():
                        continue
                    issues.extend(_archive_member_issues(rel, member.name))
                    if Path(member.name).suffix.lower() not in TEXT_EXTENSIONS:
                        continue
                    extracted = archive.extractfile(member)
                    if extracted is None:
                        continue
                    text = extracted.read().decode("utf-8", errors="replace")
                    issues.extend(scan_text(text, source=f"{rel}:{member.name}").issues)
    except Exception as exc:  # noqa: BLE001
        issues.append(f"{rel}: archive scan failed: {exc.__class__.__name__}")
    return issues


def _archive_member_issues(archive_source: str, member_name: str) -> list[str]:
    if Path(member_name).name in FORBIDDEN_ARCHIVE_MEMBERS:
        return [f"{archive_source}:{member_name}: forbidden local config packaged"]
    return []


def _relative_source(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)
