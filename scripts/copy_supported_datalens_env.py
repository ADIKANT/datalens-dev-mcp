#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path


SUPPORTED_KEYS = (
    "DATALENS_ORG_ID",
    "DATALENS_IAM_TOKEN",
    "YC_IAM_TOKEN",
    "DATALENS_BASE_URL",
    "DATALENS_API_BASE_URL",
    "DATALENS_API_VERSION",
    "DATALENS_MCP_ENABLE_WRITES",
    "DATALENS_MCP_ENABLE_EXPERT_RPC",
    "DATALENS_MCP_LIVE_ALLOW_SAVE",
    "DATALENS_MCP_LIVE_ALLOW_PUBLISH",
    "DATALENS_REQUEST_INTERVAL_SEC",
    "DATALENS_REQUEST_TIMEOUT_SEC",
    "DATALENS_RATE_LIMIT_RETRIES",
    "DATALENS_MAX_READ_CONCURRENCY",
    "DATALENS_READ_TRANSIENT_RETRIES",
    "DATALENS_REQUEST_DEBUG",
    "DATALENS_ENABLE_TOKEN_REFRESH_ON_401",
    "DATALENS_YC_BINARY",
    "DATALENS_MCP_EXPERT_ALLOW_UNSAFE_INTERNAL_NAMES",
)

RUNTIME_DEFAULTS = {
    "DATALENS_MCP_ENABLE_WRITES": "1",
    "DATALENS_MCP_ENABLE_EXPERT_RPC": "0",
    "DATALENS_MCP_LIVE_ALLOW_SAVE": "1",
    "DATALENS_MCP_LIVE_ALLOW_PUBLISH": "1",
    "DATALENS_ENABLE_TOKEN_REFRESH_ON_401": "1",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Copy supported DataLens env keys into the managed local env file.")
    parser.add_argument("--source", required=True, help="Existing dotenv file to read.")
    parser.add_argument("--target", required=True, help="Managed dotenv file to write atomically.")
    return parser.parse_args()


def read_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if key:
            values[key] = value.strip().strip("'\"")
    return values


def category(path: Path) -> str:
    text = str(path.expanduser())
    if "/.config/datalens-dev-mcp/" in text:
        return "managed_home"
    if text.endswith("/.datalens.env"):
        return "project_env_file"
    return "other_file"


def write_atomic(target: Path, lines: list[str]) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".tmp", dir=target.parent)
    tmp_path = Path(tmp_name)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write("\n".join(lines).rstrip() + "\n")
        tmp_path.replace(target)
        os.chmod(target, 0o600)
    finally:
        if tmp_path.exists():
            tmp_path.unlink()


def copy_supported(source: Path, target: Path) -> dict[str, object]:
    source_values = read_env(source)
    supported = {key: source_values[key] for key in SUPPORTED_KEYS if source_values.get(key, "").strip()}
    runtime_defaults_written: list[str] = []
    for key, value in RUNTIME_DEFAULTS.items():
        if key not in supported:
            supported[key] = value
            runtime_defaults_written.append(key)

    token_key_present = bool(supported.get("DATALENS_IAM_TOKEN") or supported.get("YC_IAM_TOKEN"))
    org_key_present = bool(supported.get("DATALENS_ORG_ID"))
    if not token_key_present or not org_key_present:
        raise SystemExit("Source file does not contain the required supported token and organization keys.")

    backup_path = ""
    if target.exists():
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        backup = target.with_name(f"{target.name}.bak.{stamp}")
        shutil.copy2(target, backup)
        os.chmod(backup, 0o600)
        backup_path = str(backup)

    lines = [
        "# Managed by datalens-dev-mcp. Keep local and untracked.",
        "# Values intentionally omitted from command output.",
    ]
    lines.extend(f"{key}={supported[key]}" for key in SUPPORTED_KEYS if key in supported)
    write_atomic(target, lines)

    return {
        "ok": True,
        "source_category": category(source),
        "target_category": category(target),
        "target_path": str(target),
        "backup_path": backup_path,
        "mode_octal": oct(target.stat().st_mode & 0o777),
        "keys_written": [key for key in SUPPORTED_KEYS if key in supported],
        "runtime_defaults_written": sorted(runtime_defaults_written),
        "unsupported_keys_skipped": sorted(key for key in source_values if key not in SUPPORTED_KEYS),
        "token_key_present": token_key_present,
        "org_key_present": org_key_present,
    }


def main() -> int:
    args = parse_args()
    result = copy_supported(Path(args.source).expanduser(), Path(args.target).expanduser())
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
