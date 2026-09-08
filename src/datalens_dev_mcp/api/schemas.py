from __future__ import annotations

import json
from importlib.resources import files
from typing import Any


class OperationRegistry:
    def __init__(self, operations: list[dict[str, Any]]) -> None:
        self._operations = {str(item["method"]): dict(item) for item in operations}

    @classmethod
    def load(cls) -> OperationRegistry:
        resource = files("datalens_dev_mcp.schemas").joinpath("supported-operations.json")
        return cls(json.loads(resource.read_text(encoding="utf-8"))["operations"])

    def get(self, method: str) -> dict[str, Any]:
        try:
            result = dict(self._operations[method])
            result.setdefault("contract_kind", "operation_metadata")
            return result
        except KeyError as exc:
            raise KeyError(f"unsupported documented DataLens method: {method}") from exc

    def list(self) -> list[dict[str, Any]]:
        return [dict(item) for item in self._operations.values()]


def get_method_schema(method: str) -> dict[str, Any]:
    return OperationRegistry.load().get(method)


def list_methods() -> list[dict[str, Any]]:
    return OperationRegistry.load().list()
