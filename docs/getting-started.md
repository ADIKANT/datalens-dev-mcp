# Getting Started

1. Install locally with `python3 -m pip install -e .`.
2. Configure the MCP server as stdio using `docs/mcp/local_stdio_contract.md`.
3. Run `python3 scripts/smoke_mcp_stdio.py` to verify stdout/stderr behavior.
4. Start with `datalens.develop_dashboard`.
5. Keep live write mode disabled until dry-run payloads and safe apply plan are reviewed.
6. Run `python3 scripts/run_offline_acceptance.py` before optional live testing.

For the complete local setup, see `docs/getting_started_local.md`.
