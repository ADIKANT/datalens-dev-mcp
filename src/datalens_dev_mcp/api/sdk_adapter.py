from __future__ import annotations

import datalens_sdk

SDK_VERSION = "0.9.0"

WIZARD_VARIANTS = {
    "area",
    "area_100p",
    "bar",
    "bar_100p",
    "column",
    "column_100p",
    "combined_chart",
    "donut",
    "flat_table",
    "funnel",
    "geolayer",
    "indicator",
    "line",
    "pie",
    "pivot_table",
    "scatter",
    "treemap",
}
EDITOR_VARIANTS = {"advanced_chart", "gravity_charts", "markdown", "selector", "table"}


class SdkAdapter:
    def __init__(self) -> None:
        actual = getattr(datalens_sdk, "__version__", "")
        if actual != SDK_VERSION:
            raise RuntimeError(f"datalens-sdk version mismatch: expected {SDK_VERSION}, got {actual or '<unknown>'}")

    def describe_factory(self, resource: str, variant: str) -> dict[str, object]:
        supported = (
            variant in WIZARD_VARIANTS
            if resource == "wizard"
            else variant in EDITOR_VARIANTS
            if resource == "editor"
            else False
        )
        return {
            "sdk_version": SDK_VERSION,
            "resource": resource,
            "variant": variant,
            "supported": supported,
            "effect": "mutation_on_build" if supported else "unsupported",
        }
