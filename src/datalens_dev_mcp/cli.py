from __future__ import annotations

import argparse

from datalens_dev_mcp import __version__
from datalens_dev_mcp.server import serve_stdio


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="datalens-dev-mcp")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    subcommands = parser.add_subparsers(dest="command")
    subcommands.add_parser("stdio", help="Run the MCP stdio server.")
    args = parser.parse_args(argv)
    if args.command in (None, "stdio"):
        serve_stdio()
        return 0
    parser.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
