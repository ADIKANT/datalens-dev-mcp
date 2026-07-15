#!/usr/bin/env python3
"""Fail closed when a repository snapshot is unsafe to publish.

The repository scan uses the current Git index plus untracked, non-ignored files,
but reads bytes from the worktree.  Consequently staged and unstaged deletions
are absent from the publication snapshot while unstaged edits are inspected.
Optional wheel, zip, and source-distribution archives can be checked as well.
"""

from __future__ import annotations

import argparse
import ipaddress
import json
import re
import stat
import subprocess
import tarfile
import zipfile
from dataclasses import asdict, dataclass
from pathlib import Path, PurePosixPath
from typing import Iterable, Iterator
from urllib.parse import parse_qsl, urlsplit


ROOT = Path(__file__).resolve().parents[1]

SCHEMA_VERSION = 1
MAX_FILE_BYTES = 16 * 1024 * 1024
MAX_ARCHIVE_BYTES = 128 * 1024 * 1024
MAX_ARCHIVE_MEMBERS = 20_000

REQUIRED_NOTICES = (
    "LICENSE",
    "LICENSES/CC-BY-4.0.txt",
    "THIRD_PARTY_NOTICES.md",
)

FORBIDDEN_TOP_LEVEL = frozenset(
    {
        ".metadata-fetch",
        "artifacts",
        "datalens_mapping",
        "dry-runs",
        "live-exports",
        "materials",
        "memory-bank",
        "raw",
        "shareable",
        "sync-local",
    }
)
FORBIDDEN_PATH_PREFIXES = (
    ("docs", "knowledge_base"),
    ("docs", "reports"),
)
FORBIDDEN_ROOT_FILES = frozenset({"run_state.md", "config/datalens_mcp.local.json"})
FORBIDDEN_PATH_PARTS = frozenset({"private_corpus"})

UNSAFE_SUFFIXES = frozenset(
    {
        ".7z",
        ".avro",
        ".bin",
        ".bz2",
        ".class",
        ".db",
        ".dll",
        ".doc",
        ".docx",
        ".dylib",
        ".exe",
        ".feather",
        ".gif",
        ".gz",
        ".ico",
        ".jar",
        ".jpeg",
        ".jpg",
        ".jks",
        ".key",
        ".parquet",
        ".pfx",
        ".pickle",
        ".pkl",
        ".png",
        ".ppt",
        ".pptx",
        ".rar",
        ".so",
        ".sqlite",
        ".sqlite3",
        ".tar",
        ".tgz",
        ".webp",
        ".whl",
        ".xls",
        ".xlsx",
        ".xz",
        ".zip",
    }
)
UNSAFE_NAMES = frozenset({"id_rsa", "id_dsa", "id_ecdsa", "id_ed25519"})

# This source file and the documentation consistency gate intentionally encode
# policy markers.  Only the marker/provenance rules are exempted; secrets,
# unsafe URLs, and all path-level rules continue to apply.
POLICY_LITERAL_PATHS = frozenset(
    {
        "scripts/check_docs_consistency.py",
        "scripts/check_public_release.py",
        "tests/unit/test_public_release_gate.py",
    }
)

UNIX_HOME_RE = re.compile(r"(?<![A-Za-z0-9_./-])/(?:Users|home)/[A-Za-z0-9._-]+(?:/|\b)")
WINDOWS_HOME_RE = re.compile(r"(?i)(?<![A-Za-z0-9_\\])\b[A-Z]:\\Users\\[A-Za-z0-9._-]+(?:\\|\b)")
EMAIL_RE = re.compile(r"(?i)\b[A-Z0-9._%+-]+@([A-Z0-9.-]+\.[A-Z]{2,})\b")
URL_RE = re.compile(r"https?://[^\s<>\"'`)\]}]+", re.IGNORECASE)

PRIVATE_KEY_RE = re.compile(r"-{5}BEGIN (?:(?:RSA|EC|DSA|OPENSSH) )?PRIVATE KEY-{5}")
PGP_PRIVATE_KEY_RE = re.compile(r"-{5}BEGIN PGP PRIVATE KEY BLOCK-{5}")
SECRET_PATTERNS = (
    re.compile(
        r"(?i)\b(?:authorization|proxy-authorization)\s*[:=]\s*"
        r"(?:bearer|basic)\s+([A-Za-z0-9._~+/=-]{12,})"
    ),
    re.compile(r"(?i)\bbearer\s+([A-Za-z0-9._~+/=-]{20,})"),
    re.compile(r"\b(?:AKIA[0-9A-Z]{16}|AQ[A-Za-z0-9_-]{30,}|y0_[A-Za-z0-9_-]{20,})\b"),
    re.compile(r"\b(?:ghp_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,}|ya29\.[A-Za-z0-9_-]{20,})\b"),
    re.compile(
        r"(?i)\b(?:api[_-]?key|access[_-]?token|auth[_-]?token|iam[_-]?token|"
        r"password|passwd|secret)\b\s*[:=]\s*[\"']?([A-Za-z0-9._~+/@:=-]{16,})"
    ),
    re.compile(
        r"(?i)\b(?:postgres(?:ql)?|mysql|mongodb(?:\+srv)?|redis)://"
        r"[^/\s:@]+:([^@\s/]{8,})@"
    ),
)
PLACEHOLDER_MARKERS = (
    "dummy",
    "example",
    "fake",
    "fixture",
    "must-not-leak",
    "placeholder",
    "secret-token-value",
    "should-redact",
    "synthetic",
    "test-token",
)

PROVENANCE_PATTERNS = (
    re.compile(r"(?i)\bmaterials?/(?:raw|extract(?:ed|ion)?|sources?|books?|courses?|pdfs?)(?:/|\b)"),
    re.compile(r"(?i)\bsource\s+trace\s*:.*\.pdf\b"),
    re.compile(r"(?i)\.pdf\b.{0,80}\bpages?\s+\d+(?:\s*[-–]\s*\d+)?\b"),
    re.compile(r"(?i)\bfull\s+extract(?:ion|ed)?\b.{0,80}\b(?:book|course|guide|pdf|publication)\b"),
    re.compile(r"(?i)\b(?:distill(?:ed|ation)?|derived)\b.{0,80}\b(?:book|course|pdf|local\s+material)\b"),
)

ALLOWED_EMAIL_DOMAINS = frozenset(
    {
        "example.com",
        "example.invalid",
        "example.test",
        "users.noreply.github.com",
    }
)
SAFE_LOCAL_SCHEMA_HOSTS = frozenset({"datalens-dev-mcp.local", "schemas.local"})
INTERNAL_HOST_SUFFIXES = (".corp", ".internal", ".lan", ".local")
SENSITIVE_QUERY_KEYS = frozenset(
    {
        "access_token",
        "api_key",
        "apikey",
        "auth",
        "authorization",
        "key",
        "password",
        "secret",
        "token",
    }
)
OBJECT_URL_RE = re.compile(r"(?i)/(?:charts?|dashboards?|datasets?|workbooks?)/([^/?#]+)")
DATALENS_SHAPED_ID_RE = re.compile(r"\b(?=[a-z0-9]{0,12}\d)[a-z0-9]{13}\b")
SYNTHETIC_ID_PREFIXES = ("demo", "synthetic")
OFFICIAL_DOC_ID_PATH_SUFFIXES = (
    "assets/schemas/datalens-knowledge/rule-cards.jsonl",
)


@dataclass(frozen=True, order=True)
class Issue:
    category: str
    path: str
    message: str
    line: int | None = None

    def as_dict(self) -> dict[str, object]:
        return {key: value for key, value in asdict(self).items() if value is not None}


def _path_issue(rel: str) -> Issue | None:
    pure = PurePosixPath(rel)
    parts = pure.parts
    if not parts:
        return None
    folded_parts = tuple(part.casefold() for part in parts)
    if folded_parts[0] in FORBIDDEN_TOP_LEVEL:
        return Issue("forbidden_path", rel, "forbidden top-level publication artifact")
    if any(folded_parts[: len(prefix)] == prefix for prefix in FORBIDDEN_PATH_PREFIXES):
        return Issue("forbidden_path", rel, "forbidden generated or mirrored documentation tree")
    if rel.casefold() in FORBIDDEN_ROOT_FILES:
        return Issue("forbidden_path", rel, "private state or local configuration must not be published")
    if any(part in FORBIDDEN_PATH_PARTS for part in folded_parts):
        return Issue("forbidden_path", rel, "private corpus path must not be published")
    name = pure.name.casefold()
    if name == ".env" or (name.startswith(".env.") and name not in {".env.example", ".env.sample"}):
        return Issue("forbidden_path", rel, "environment file must not be published")
    if name in UNSAFE_NAMES or pure.suffix.casefold() in UNSAFE_SUFFIXES:
        return Issue("unsafe_file_type", rel, "binary, archive, credential, or raw-data file type is not allowed")
    return None


def _git_publication_files(root: Path) -> tuple[list[tuple[str, Path]], list[Issue]]:
    command = ["git", "-C", str(root), "ls-files", "-z", "--cached", "--others", "--exclude-standard"]
    try:
        result = subprocess.run(command, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except (OSError, subprocess.CalledProcessError) as exc:
        return [], [Issue("git_inventory_error", ".", f"cannot determine publication snapshot: {type(exc).__name__}")]

    files: list[tuple[str, Path]] = []
    seen: set[str] = set()
    for raw in result.stdout.split(b"\0"):
        if not raw:
            continue
        rel = raw.decode("utf-8", errors="surrogateescape").replace("\\", "/")
        if rel in seen:
            continue
        seen.add(rel)
        path = root / rel
        # Index entries removed from the worktree are not part of the snapshot.
        # Existing paths are read from the worktree, so unstaged edits are seen.
        if path.is_symlink() or path.is_file():
            files.append((rel, path))
    return sorted(files), []


def _filesystem_publication_files(root: Path) -> tuple[list[tuple[str, Path]], list[Issue]]:
    files: list[tuple[str, Path]] = []
    skipped_dirs = {".git", ".mypy_cache", ".pytest_cache", ".ruff_cache", "__pycache__"}
    for path in root.rglob("*"):
        try:
            rel_path = path.relative_to(root)
        except ValueError:
            continue
        if any(part in skipped_dirs for part in rel_path.parts):
            continue
        if path.is_symlink() or path.is_file():
            files.append((rel_path.as_posix(), path))
    return sorted(files), []


def _publication_files(root: Path) -> tuple[list[tuple[str, Path]], list[Issue]]:
    if (root / ".git").exists():
        return _git_publication_files(root)
    return _filesystem_publication_files(root)


def _placeholder_line(line: str) -> bool:
    folded = line.casefold()
    return any(marker in folded for marker in PLACEHOLDER_MARKERS)


def _placeholder_match(match: re.Match[str]) -> bool:
    captured = " ".join(value for value in match.groups() if value)
    return _placeholder_line(captured or match.group(0))


def _line_number(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def _is_official_yandex_url(host: str, path: str) -> bool:
    official_hosts = {
        "api.datalens.tech",
        "datalens.ru",
        "datalens.yandex.cloud",
        "docs.yandex.cloud",
        "yandex.cloud",
        "ya.ru",
    }
    official_suffixes = (".yandexcloud.net", ".yastatic.net")
    if host in official_hosts or host.endswith(official_suffixes):
        return True
    if host in {"github.com", "raw.githubusercontent.com"}:
        return path.casefold().startswith("/yandex-cloud/")
    return False


def _url_issue(url: str) -> str | None:
    try:
        parsed = urlsplit(url)
        host = (parsed.hostname or "").casefold().rstrip(".")
        port = parsed.port
    except ValueError:
        # Broken URL literals are not reachable internal resources.  Other
        # quality gates may reject them, but they are not publication leaks.
        return None
    if not host:
        return "URL has no host"

    if parsed.username is not None or parsed.password is not None:
        return "URL contains embedded credentials"
    if any(key.casefold() in SENSITIVE_QUERY_KEYS for key, _ in parse_qsl(parsed.query, keep_blank_values=True)):
        return "URL contains a sensitive query parameter"
    if host in {"example.com", "example.invalid", "example.test"}:
        return None

    if host not in SAFE_LOCAL_SCHEMA_HOSTS:
        try:
            address = ipaddress.ip_address(host)
        except ValueError:
            address = None
        if address is not None and (
            address.is_private or address.is_loopback or address.is_link_local or address.is_reserved
        ):
            return "URL points to a non-public network address"
        if host == "localhost" or host.endswith(INTERNAL_HOST_SUFFIXES):
            return "URL points to an internal or local host"
        labels = set(host.split("."))
        if labels.intersection({"confluence", "intranet", "jira", "trino"}):
            return "URL appears to point to an internal service"

    if _is_official_yandex_url(host, parsed.path):
        # Documentation URLs may contain singular nouns such as /chart/<page>;
        # they are not deployment-object links.  Concrete object URLs are only
        # meaningful on the interactive DataLens hosts.
        if host == "datalens.yandex.cloud" or host == "datalens.ru" or host.endswith(".datalens.ru"):
            match = OBJECT_URL_RE.search(parsed.path)
            if match and "_" not in match.group(1):
                return "URL appears to identify a concrete DataLens object"
        return None
    if OBJECT_URL_RE.search(parsed.path) and "datalens" in host:
        return "URL appears to identify a concrete DataLens object"
    _ = port  # Accessing parsed.port above validates the value.
    return None


def _scan_text(text: str, display_path: str, policy_rel: str | None = None) -> list[Issue]:
    issues: list[Issue] = []
    literal_policy_source = policy_rel in POLICY_LITERAL_PATHS

    for pattern in (PRIVATE_KEY_RE, PGP_PRIVATE_KEY_RE):
        for match in pattern.finditer(text):
            issues.append(
                Issue(
                    "secret",
                    display_path,
                    "private key material marker is present",
                    _line_number(text, match.start()),
                )
            )

    for pattern in SECRET_PATTERNS:
        for match in pattern.finditer(text):
            if _placeholder_match(match):
                continue
            issues.append(
                Issue("secret", display_path, "credential-like value is present", _line_number(text, match.start()))
            )

    if not literal_policy_source:
        for pattern in (UNIX_HOME_RE, WINDOWS_HOME_RE):
            for match in pattern.finditer(text):
                issues.append(
                    Issue(
                        "absolute_local_path",
                        display_path,
                        "absolute local user path is present",
                        _line_number(text, match.start()),
                    )
                )
        for pattern in PROVENANCE_PATTERNS:
            for match in pattern.finditer(text):
                issues.append(
                    Issue(
                        "source_material_provenance",
                        display_path,
                        "raw or publication-derived source-material trace is present",
                        _line_number(text, match.start()),
                    )
                )

    for match in EMAIL_RE.finditer(text):
        domain = match.group(1).casefold().rstrip(".")
        if domain not in ALLOWED_EMAIL_DOMAINS:
            issues.append(
                Issue(
                    "internal_email",
                    display_path,
                    "non-placeholder email address is present",
                    _line_number(text, match.start()),
                )
            )

    for match in URL_RE.finditer(text):
        reason = _url_issue(match.group(0))
        if reason:
            issues.append(Issue("internal_url", display_path, reason, _line_number(text, match.start())))

    official_doc_examples = bool(
        policy_rel and any(policy_rel.endswith(suffix) for suffix in OFFICIAL_DOC_ID_PATH_SUFFIXES)
    )
    if not official_doc_examples:
        for match in DATALENS_SHAPED_ID_RE.finditer(text):
            value = match.group(0)
            if value.startswith(SYNTHETIC_ID_PREFIXES):
                continue
            issues.append(
                Issue(
                    "concrete_datalens_id",
                    display_path,
                    "DataLens-shaped identifier must be replaced with an explicit synthetic placeholder",
                    _line_number(text, match.start()),
                )
            )

    # One actionable finding per file/category/reason keeps large generated
    # manifests readable without weakening the fail-closed result.
    unique: dict[tuple[str, str, str], Issue] = {}
    for issue in sorted(set(issues)):
        unique.setdefault((issue.category, issue.path, issue.message), issue)
    return sorted(unique.values())


def _decode_text(data: bytes, display_path: str) -> tuple[str | None, Issue | None]:
    if len(data) > MAX_FILE_BYTES:
        return None, Issue("oversized_file", display_path, f"file exceeds {MAX_FILE_BYTES} bytes")
    if b"\0" in data:
        return None, Issue("unsafe_binary", display_path, "NUL bytes indicate binary content")
    try:
        return data.decode("utf-8"), None
    except UnicodeDecodeError:
        return None, Issue("unsafe_binary", display_path, "file is not valid UTF-8 text")


def _scan_repository_file(rel: str, path: Path) -> list[Issue]:
    if path.is_symlink():
        return [Issue("symlink", rel, "symbolic links are not allowed in the public snapshot")]
    path_problem = _path_issue(rel)
    if path_problem is not None:
        return [path_problem]
    try:
        data = path.read_bytes()
    except OSError as exc:
        return [Issue("read_error", rel, f"cannot read publication file: {type(exc).__name__}")]
    text, decode_problem = _decode_text(data, rel)
    if decode_problem is not None:
        return [decode_problem]
    assert text is not None
    return _scan_text(text, rel, policy_rel=rel)


def _safe_archive_name(name: str) -> bool:
    if not name or "\\" in name:
        return False
    pure = PurePosixPath(name)
    return not pure.is_absolute() and ".." not in pure.parts


def _common_archive_root(names: Iterable[str]) -> str | None:
    roots: set[str] = set()
    for name in names:
        parts = PurePosixPath(name).parts
        if len(parts) < 2:
            return None
        roots.add(parts[0])
        if len(roots) > 1:
            return None
    return next(iter(roots)) if roots else None


def _without_archive_root(name: str, common_root: str | None) -> str:
    parts = PurePosixPath(name).parts
    if common_root and len(parts) > 1 and parts[0] == common_root:
        return PurePosixPath(*parts[1:]).as_posix()
    return name


def _archive_notice_key(name: str) -> str | None:
    folded = name.casefold().strip("/")
    candidates = {
        "LICENSE": ("license",),
        "LICENSES/CC-BY-4.0.txt": ("licenses/cc-by-4.0.txt",),
        "THIRD_PARTY_NOTICES.md": ("third_party_notices.md",),
    }
    for required, suffixes in candidates.items():
        if any(folded == suffix or folded.endswith("/" + suffix) for suffix in suffixes):
            return required
    return None


def _scan_archive_member(
    name: str,
    data: bytes,
    archive_label: str,
    *,
    policy_name: str | None = None,
) -> list[Issue]:
    display = f"{archive_label}!{name}"
    problem = _path_issue(policy_name or name)
    if problem is not None:
        return [Issue(problem.category, display, problem.message)]
    text, decode_problem = _decode_text(data, display)
    if decode_problem is not None:
        return [decode_problem]
    assert text is not None
    return _scan_text(text, display, policy_rel=policy_name or name)


def _scan_zip_archive(path: Path, archive_label: str) -> list[Issue]:
    issues: list[Issue] = []
    notices: set[str] = set()
    total_size = 0
    try:
        with zipfile.ZipFile(path) as archive:
            members = archive.infolist()
            if len(members) > MAX_ARCHIVE_MEMBERS:
                return [Issue("archive_limit", archive_label, "archive has too many members")]
            safe_file_names = [
                member.filename
                for member in members
                if not member.is_dir() and _safe_archive_name(member.filename)
            ]
            common_root = _common_archive_root(safe_file_names)
            for member in members:
                name = member.filename
                if not _safe_archive_name(name):
                    issues.append(Issue("archive_path", f"{archive_label}!{name}", "unsafe archive member path"))
                    continue
                mode = member.external_attr >> 16
                if stat.S_ISLNK(mode):
                    issues.append(Issue("archive_symlink", f"{archive_label}!{name}", "archive symlink is not allowed"))
                    continue
                if member.is_dir():
                    continue
                total_size += member.file_size
                if member.file_size > MAX_FILE_BYTES or total_size > MAX_ARCHIVE_BYTES:
                    issues.append(Issue("archive_limit", f"{archive_label}!{name}", "archive expansion limit exceeded"))
                    continue
                notice = _archive_notice_key(name)
                if notice:
                    notices.add(notice)
                try:
                    data = archive.read(member)
                except (OSError, RuntimeError, zipfile.BadZipFile):
                    issues.append(Issue("archive_read_error", f"{archive_label}!{name}", "cannot read archive member"))
                    continue
                issues.extend(
                    _scan_archive_member(
                        name,
                        data,
                        archive_label,
                        policy_name=_without_archive_root(name, common_root),
                    )
                )
    except (OSError, zipfile.BadZipFile, zipfile.LargeZipFile):
        return [Issue("archive_read_error", archive_label, "cannot open zip or wheel archive")]

    for required in REQUIRED_NOTICES:
        if required not in notices:
            issues.append(Issue("archive_missing_notice", archive_label, f"archive is missing {required}"))
    return issues


def _scan_tar_archive(path: Path, archive_label: str) -> list[Issue]:
    issues: list[Issue] = []
    notices: set[str] = set()
    total_size = 0
    try:
        with tarfile.open(path, mode="r:*") as archive:
            members = archive.getmembers()
            if len(members) > MAX_ARCHIVE_MEMBERS:
                return [Issue("archive_limit", archive_label, "archive has too many members")]
            safe_file_names = [member.name for member in members if member.isfile() and _safe_archive_name(member.name)]
            common_root = _common_archive_root(safe_file_names)
            for member in members:
                name = member.name
                if not _safe_archive_name(name):
                    issues.append(Issue("archive_path", f"{archive_label}!{name}", "unsafe archive member path"))
                    continue
                if member.isdir():
                    continue
                if not member.isfile():
                    issues.append(
                        Issue(
                            "archive_symlink",
                            f"{archive_label}!{name}",
                            "archive link or special file is not allowed",
                        )
                    )
                    continue
                total_size += member.size
                if member.size > MAX_FILE_BYTES or total_size > MAX_ARCHIVE_BYTES:
                    issues.append(Issue("archive_limit", f"{archive_label}!{name}", "archive expansion limit exceeded"))
                    continue
                notice = _archive_notice_key(name)
                if notice:
                    notices.add(notice)
                extracted = archive.extractfile(member)
                if extracted is None:
                    issues.append(Issue("archive_read_error", f"{archive_label}!{name}", "cannot read archive member"))
                    continue
                try:
                    data = extracted.read(MAX_FILE_BYTES + 1)
                except OSError:
                    issues.append(Issue("archive_read_error", f"{archive_label}!{name}", "cannot read archive member"))
                    continue
                issues.extend(
                    _scan_archive_member(
                        name,
                        data,
                        archive_label,
                        policy_name=_without_archive_root(name, common_root),
                    )
                )
    except (OSError, tarfile.TarError):
        return [Issue("archive_read_error", archive_label, "cannot open source-distribution archive")]

    for required in REQUIRED_NOTICES:
        if required not in notices:
            issues.append(Issue("archive_missing_notice", archive_label, f"archive is missing {required}"))
    return issues


def _scan_archive(path: Path, root: Path) -> list[Issue]:
    try:
        label = path.relative_to(root).as_posix()
    except ValueError:
        label = path.name
    folded = path.name.casefold()
    if not path.is_file():
        return [Issue("archive_read_error", label, "archive does not exist or is not a regular file")]
    if folded.endswith((".whl", ".zip")):
        return _scan_zip_archive(path, label)
    if folded.endswith((".tar", ".tar.gz", ".tgz")):
        return _scan_tar_archive(path, label)
    return [Issue("archive_type", label, "unsupported archive type; expected wheel, zip, tar, tar.gz, or tgz")]


def _normalized_archives(root: Path, archives: Iterable[Path | str]) -> Iterator[Path]:
    seen: set[Path] = set()
    for value in archives:
        path = Path(value).expanduser()
        if not path.is_absolute():
            path = root / path
        path = path.resolve(strict=False)
        if path not in seen:
            seen.add(path)
            yield path


def run_check(root: Path = ROOT, archives: Iterable[Path | str] = ()) -> dict[str, object]:
    root = Path(root).expanduser().resolve(strict=False)
    files, inventory_issues = _publication_files(root)
    issues = list(inventory_issues)
    effective_paths = {rel for rel, _ in files}

    for required in REQUIRED_NOTICES:
        required_path = root / required
        if required not in effective_paths or not required_path.is_file() or required_path.is_symlink():
            issues.append(Issue("missing_notice", required, "required public-release notice is missing"))

    for rel, path in files:
        issues.extend(_scan_repository_file(rel, path))

    archive_paths = list(_normalized_archives(root, archives))
    for archive in archive_paths:
        issues.extend(_scan_archive(archive, root))

    ordered = sorted(set(issues))
    return {
        "ok": not ordered,
        "schema_version": SCHEMA_VERSION,
        "root": str(root),
        "file_count": len(files),
        "archive_count": len(archive_paths),
        "issue_count": len(ordered),
        "issues": [issue.as_dict() for issue in ordered],
    }


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT, help="repository root (default: script parent)")
    parser.add_argument("--archive", action="append", type=Path, default=[], help="wheel/sdist archive to inspect")
    parser.add_argument("archives", nargs="*", type=Path, help="additional wheel/sdist archives")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    report = run_check(args.root, [*args.archive, *args.archives])
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
