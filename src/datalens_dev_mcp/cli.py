from __future__ import annotations

import argparse
import json
from pathlib import Path

from datalens_dev_mcp import __version__
from datalens_dev_mcp.mcp.tools.pipeline import dl_start_pipeline, dl_validate_project
from datalens_dev_mcp.server import serve_stdio
from datalens_dev_mcp.validators.security_validator import scan_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="datalens-dev-mcp")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command")
    stdio = sub.add_parser("stdio", help="Run MCP stdio server.")
    stdio.add_argument("--project-root", default=".")
    stdio.add_argument("--local-config", default=None)
    init = sub.add_parser("init", help="Scaffold a local DataLens project.")
    init.add_argument("project_root", nargs="?", default=".")
    init.add_argument("--scenario", default="new_dashboard")
    init.add_argument("--dashboard-name", default="Synthetic Dashboard")
    validate = sub.add_parser("validate", help="Run offline project validation.")
    validate.add_argument("project_root", nargs="?", default=".")
    scan = sub.add_parser("scan", help="Run the secret-only scanner.")
    scan.add_argument("path", nargs="?", default=".")
    args = parser.parse_args(argv)

    if args.command in (None, "stdio"):
        serve_stdio(project_root=getattr(args, "project_root", "."), local_config_path=getattr(args, "local_config", None))
        return 0
    if args.command == "init":
        print(json.dumps(dl_start_pipeline(args.project_root, args.scenario, args.dashboard_name), indent=2))
        return 0
    if args.command == "validate":
        result = dl_validate_project(args.project_root)
        print(json.dumps(result, indent=2))
        return 0 if result["status"] == "pass" else 1
    if args.command == "scan":
        result = scan_path(Path(args.path))
        print(json.dumps({"ok": result.ok, "issues": result.issues}, indent=2))
        return 0 if result.ok else 1
    parser.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
