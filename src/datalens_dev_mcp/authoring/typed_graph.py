from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from datalens_sdk import DashboardTab

_DATASET_KINDS = frozenset({"dimension", "measure"})


def dataset_builder(client: Any, connection: Any, specification: Mapping[str, Any], *, name: str, location: Any) -> Any:
    """Build one Dataset from a known connection through SDK 0.9 typed builders.

    This function only configures a builder. Its caller owns the single external
    ``build()`` mutation and the subsequent readback.
    """
    allowed = {"connection_id", "source", "fields", "parameters", "description"}
    if set(specification) - allowed:
        raise ValueError(f"unsupported Dataset settings: {sorted(set(specification) - allowed)}")
    connection_id = specification.get("connection_id")
    if not isinstance(connection_id, str) or not connection_id or str(getattr(connection, "id", "")) != connection_id:
        raise ValueError("Dataset connection_id must match the fetched connection")
    raw_source = specification.get("source")
    if not isinstance(raw_source, Mapping):
        raise TypeError("Dataset source must be an object")
    if set(raw_source) - {"alias", "source_type", "parameters"}:
        raise ValueError(
            f"unsupported Dataset source settings: {sorted(set(raw_source) - {'alias', 'source_type', 'parameters'})}"
        )
    alias, source_type = raw_source.get("alias"), raw_source.get("source_type")
    parameters = raw_source.get("parameters") or {}
    if not isinstance(alias, str) or not alias or not isinstance(source_type, str) or not source_type:
        raise ValueError("Dataset source requires alias and source_type")
    if not isinstance(parameters, Mapping):
        raise TypeError("Dataset source parameters must be an object")
    source = client.create.source(using=connection).raw(
        alias=alias,
        source_type=source_type.upper(),
        parameters=dict(parameters),
    )
    builder = client.create.dataset(name=name, location=location).add_source(source)
    if specification.get("description") is not None:
        builder.description(str(specification["description"]))
    fields = specification.get("fields") or []
    if not isinstance(fields, list) or not fields:
        raise ValueError("Dataset fields must be a nonempty list")
    seen: set[str] = set()
    for index, field in enumerate(fields):
        if not isinstance(field, Mapping):
            raise TypeError(f"Dataset field {index} must be an object")
        guid = field.get("guid")
        title = field.get("title") or field.get("name")
        kind = str(field.get("kind") or field.get("type") or "").lower()
        if kind not in _DATASET_KINDS:
            raise ValueError(f"Dataset field {index} kind must be dimension or measure")
        if not isinstance(guid, str) or not guid or guid in seen or not isinstance(title, str) or not title:
            raise ValueError("Dataset fields require unique GUIDs and nonempty titles")
        seen.add(guid)
        if field.get("formula") is not None:
            formula = field["formula"]
            if not isinstance(formula, str) or not formula:
                raise ValueError(f"Dataset calculation {guid} requires a formula")
            kwargs: dict[str, Any] = {
                "name": title,
                "formula": formula,
                "kind": kind,
                "guid": guid,
            }
            if "aggregation" in field:
                kwargs["aggregation"] = field["aggregation"]
            if field.get("cast"):
                kwargs["cast"] = field["cast"]
            builder.add_calculation(**kwargs)
            continue
        source_name = field.get("source")
        if not isinstance(source_name, str) or not source_name:
            raise ValueError(f"Dataset direct field {guid} requires source")
        kwargs = {
            "title": title,
            "source": source_name,
            "kind": kind,
            "avatar_id": source.id,
            "guid": guid,
        }
        for key in ("aggregation", "cast", "description", "hidden"):
            if key in field:
                kwargs[key] = field[key]
        builder.add_field(**kwargs)
    parameters_spec = specification.get("parameters") or []
    if not isinstance(parameters_spec, list):
        raise TypeError("Dataset parameters must be a list")
    for parameter in parameters_spec:
        if not isinstance(parameter, Mapping):
            raise TypeError("Dataset parameter must be an object")
        required = (parameter.get("name"), parameter.get("type"), parameter.get("default"))
        if (
            not isinstance(required[0], str)
            or not required[0]
            or not isinstance(required[1], str)
            or required[2] is None
        ):
            raise ValueError("Dataset parameter requires name, type and default")
        builder.add_parameter(
            name=required[0],
            type=required[1],
            default=required[2],
            guid=str(parameter["guid"]) if parameter.get("guid") else None,
        )
    return builder


def dashboard_builder(client: Any, specification: Mapping[str, Any], *, name: str, location: Any) -> Any:
    """Build dashboard tabs/widgets using the official DashboardTab surface."""
    if set(specification) - {"tabs", "settings", "description"}:
        raise ValueError(
            f"unsupported dashboard settings: {sorted(set(specification) - {'tabs', 'settings', 'description'})}"
        )
    tabs = specification.get("tabs")
    if not isinstance(tabs, list) or not tabs:
        raise ValueError("dashboard.tabs must be a nonempty list")
    builder = client.create.dashboard(name=name, location=location)
    if specification.get("description") is not None:
        builder.description(str(specification["description"]))
    for raw_tab in tabs:
        if not isinstance(raw_tab, Mapping) or not isinstance(raw_tab.get("title"), str) or not raw_tab["title"]:
            raise ValueError("dashboard tab requires a title")
        tab = DashboardTab(
            str(raw_tab["title"]),
            tab_id=str(raw_tab["tab_id"]) if raw_tab.get("tab_id") else None,
            hidden=bool(raw_tab.get("hidden", False)),
        )
        items = raw_tab.get("items") or []
        if not isinstance(items, list) or not items:
            raise ValueError("dashboard tab requires items")
        for item in items:
            if not isinstance(item, Mapping):
                raise TypeError("dashboard item must be an object")
            kind = item.get("kind")
            at = _tuple(item.get("at"), length=4, name="item.at")
            item_id = str(item["item_id"]) if item.get("item_id") else None
            title = item.get("title")
            if kind == "chart":
                chart_id = item.get("chart_id")
                if not isinstance(chart_id, str) or not chart_id or not isinstance(title, str) or not title:
                    raise ValueError("dashboard chart requires chart_id and title")
                tab.add_chart(
                    chart_id,
                    title=title,
                    item_id=item_id,
                    at=at,
                    size=_tuple(item.get("size"), length=2, name="item.size", optional=True),
                    show_title=bool(item.get("show_title", True)),
                    auto_height=bool(item.get("auto_height", False)),
                    hint=str(item["hint"]) if item.get("hint") is not None else None,
                )
            elif kind == "external_selector":
                chart_id = item.get("chart_id")
                if not isinstance(chart_id, str) or not chart_id or not isinstance(title, str) or not title:
                    raise ValueError("external selector requires chart_id and title")
                tab.add_selector(chart=chart_id, title=title, item_id=item_id, at=at)
            elif kind == "title":
                if not isinstance(title, str) or not title:
                    raise ValueError("dashboard title item requires title")
                tab.add_title(title, item_id=item_id, at=at)
            elif kind == "text":
                text = item.get("text")
                if not isinstance(text, str) or not text:
                    raise ValueError("dashboard text item requires text")
                tab.add_text(text, item_id=item_id, at=at)
            else:
                raise ValueError(f"unsupported dashboard item kind: {kind}")
        builder.add_tab(tab)
    settings = specification.get("settings") or {}
    if not isinstance(settings, Mapping):
        raise TypeError("dashboard settings must be an object")
    if settings:
        builder.settings(**dict(settings))
    return builder


def _tuple(value: Any, *, length: int, name: str, optional: bool = False) -> tuple[int, ...] | None:
    if value is None and optional:
        return None
    if not isinstance(value, (list, tuple)) or len(value) != length or any(type(item) is not int for item in value):
        raise ValueError(f"{name} must contain {length} integers")
    return tuple(value)
