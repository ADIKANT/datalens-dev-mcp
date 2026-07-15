from __future__ import annotations

from datalens_dev_mcp.knowledge.formulas import validate_formula_expression
from datalens_dev_mcp.knowledge.reference import build_reference_response

__all__ = ["DEFAULT_CORPUS_ROOT", "build_reference_response", "validate_formula_expression"]


def __getattr__(name: str):
    if name == "DEFAULT_CORPUS_ROOT":
        from datalens_dev_mcp.knowledge.compiler import DEFAULT_CORPUS_ROOT

        return DEFAULT_CORPUS_ROOT
    raise AttributeError(name)
