"""Print one MCP result once, preferring structuredContent over compatibility text.

Usage: python scripts/print_tool_result.py < call-tool-result.json
Accepts a CallToolResult or its JSON-RPC response envelope. No provider calls.
"""

from __future__ import annotations

import json
import sys


def main() -> int:
    envelope = json.load(sys.stdin)
    if "error" in envelope and "jsonrpc" in envelope:
        print(json.dumps(envelope["error"], ensure_ascii=False))
        return 1
    result = envelope.get("result", envelope)
    if "structuredContent" in result:
        print(json.dumps(result["structuredContent"], ensure_ascii=False))
    else:
        for item in result.get("content", []):
            if item.get("type") == "text":
                print(item["text"])
    return 1 if result.get("isError") else 0


if __name__ == "__main__":
    raise SystemExit(main())
