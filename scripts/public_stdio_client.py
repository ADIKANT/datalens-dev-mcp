#!/usr/bin/env python3
"""Minimal JSON-RPC client for an installed DataLens MCP stdio process."""

from __future__ import annotations

import json
import os
import selectors
import subprocess
import time
from pathlib import Path
from typing import Any, Self


class PublicStdioError(RuntimeError):
    pass


class PublicStdioClient:
    def __init__(
        self,
        command: list[str],
        *,
        cwd: str | Path,
        env: dict[str, str] | None = None,
        timeout: float = 90.0,
        stderr_path: str | Path | None = None,
    ) -> None:
        self.command = list(command)
        self.cwd = str(Path(cwd).resolve())
        self.env = dict(os.environ if env is None else env)
        self.timeout = max(1.0, float(timeout))
        self.stderr_path = Path(stderr_path).resolve() if stderr_path else None
        self._stderr = None
        self._process: subprocess.Popen[str] | None = None
        self._next_id = 1

    def __enter__(self) -> Self:
        self.start()
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def start(self) -> None:
        if self._process is not None:
            return
        if self.stderr_path:
            self.stderr_path.parent.mkdir(parents=True, exist_ok=True)
            self._stderr = self.stderr_path.open("w", encoding="utf-8")
        self._process = subprocess.Popen(
            self.command,
            cwd=self.cwd,
            env=self.env,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=self._stderr or subprocess.DEVNULL,
            text=True,
            bufsize=1,
        )

    def initialize(self) -> dict[str, Any]:
        result = self.request(
            "initialize",
            {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": "datalens-public-canary", "version": "1"},
            },
        )
        self.notify("notifications/initialized")
        return result

    def list_tools(self) -> dict[str, Any]:
        return self.request("tools/list")

    def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        result = self.request("tools/call", {"name": name, "arguments": arguments})
        contents = result.get("content") if isinstance(result, dict) else None
        if not isinstance(contents, list) or not contents:
            raise PublicStdioError(f"tool {name} returned no MCP content")
        text = str((contents[0] if isinstance(contents[0], dict) else {}).get("text") or "")
        try:
            payload = json.loads(text)
        except json.JSONDecodeError as exc:
            raise PublicStdioError(f"tool {name} returned non-JSON text") from exc
        if result.get("isError") is True:
            raise PublicStdioError(f"tool {name} failed: {_compact(payload)}")
        if not isinstance(payload, dict):
            raise PublicStdioError(f"tool {name} returned a non-object payload")
        return payload

    def request(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        request_id = self._next_id
        self._next_id += 1
        message: dict[str, Any] = {"jsonrpc": "2.0", "id": request_id, "method": method}
        if params is not None:
            message["params"] = params
        self._write(message)
        deadline = time.monotonic() + self.timeout
        while True:
            response = self._read(deadline)
            if response.get("id") != request_id:
                continue
            if "error" in response:
                raise PublicStdioError(f"JSON-RPC {method} failed: {_compact(response['error'])}")
            result = response.get("result")
            if not isinstance(result, dict):
                raise PublicStdioError(f"JSON-RPC {method} returned no object result")
            return result

    def notify(self, method: str, params: dict[str, Any] | None = None) -> None:
        message: dict[str, Any] = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            message["params"] = params
        self._write(message)

    def close(self) -> None:
        process = self._process
        self._process = None
        if process is not None:
            if process.stdin:
                process.stdin.close()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
        if self._stderr:
            self._stderr.close()
            self._stderr = None

    def _write(self, message: dict[str, Any]) -> None:
        if self._process is None or self._process.stdin is None:
            raise PublicStdioError("stdio process is not running")
        self._process.stdin.write(json.dumps(message, ensure_ascii=False, separators=(",", ":")) + "\n")
        self._process.stdin.flush()

    def _read(self, deadline: float) -> dict[str, Any]:
        if self._process is None or self._process.stdout is None:
            raise PublicStdioError("stdio process is not running")
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise PublicStdioError("timed out waiting for stdio JSON-RPC response")
        selector = selectors.DefaultSelector()
        try:
            selector.register(self._process.stdout, selectors.EVENT_READ)
            if not selector.select(remaining):
                raise PublicStdioError("timed out waiting for stdio JSON-RPC response")
        finally:
            selector.close()
        line = self._process.stdout.readline()
        if not line:
            code = self._process.poll()
            raise PublicStdioError(f"stdio process ended before a response (returncode={code})")
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            raise PublicStdioError("stdio process emitted non-JSON stdout") from exc
        if not isinstance(value, dict):
            raise PublicStdioError("stdio process emitted a non-object JSON-RPC response")
        return value


def _compact(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))[:800]
