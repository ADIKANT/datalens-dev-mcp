# Getting Started

The Russian documentation hub is the default public entry point:
[`docs/README.md`](README.md). An English mirror is available at
[`docs/README_en.md`](README_en.md).

1. Install the package from the root [README](../README_en.md#installation).
2. Configure the MCP server as stdio using
   [`docs/mcp/local_stdio_contract.md`](mcp/local_stdio_contract.md).
3. Run `python3 scripts/smoke_mcp_stdio.py` to verify stdout/stderr behavior.
4. Start with `dl_runtime_status`, `dl_auth_probe`, and the read-only discovery
   sequence in the [usage flow](usage-flow_en.md).
5. Keep live writes disabled until the payload and safe-apply plans have been
   reviewed.
6. Run `python3 scripts/run_offline_acceptance.py` before optional live testing.

Normal user workflows use only the 38 tools returned by standard `tools/list`.
Compatibility/test-only tools are not a user-selectable profile.
