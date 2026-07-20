from __future__ import annotations


NUMERIC_FIELD_TYPES = {
    "decimal",
    "double",
    "float",
    "float32",
    "float64",
    "int",
    "int16",
    "int32",
    "int64",
    "int8",
    "integer",
    "long",
    "measure",
    "number",
    "numeric",
    "real",
    "short",
    "uint",
    "uint16",
    "uint32",
    "uint64",
    "uint8",
}
GEO_FIELD_TYPES = {
    "geo",
    "geopoint",
    "geopolygon",
    "lat_lon",
    "latitude_longitude",
    "point",
    "polygon",
}


def binding_role_type_error(*, visualization_id: str, role: str, field_type: str) -> str:
    normalized_type = normalize_field_type(field_type)
    if not normalized_type:
        return ""
    expected = expected_role_type(visualization_id=visualization_id, role=role)
    if expected == "numeric" and normalized_type not in NUMERIC_FIELD_TYPES:
        return f"requires a numeric field, got {field_type}"
    if expected == "geo" and normalized_type not in GEO_FIELD_TYPES:
        return f"requires a geographic field, got {field_type}"
    return ""


def expected_role_type(*, visualization_id: str, role: str) -> str:
    normalized_role = role.strip().lower()
    if normalized_role == "geo":
        return "geo"
    if normalized_role in {"measures", "measure", "size"}:
        return "numeric"
    if normalized_role in {"y", "y2"}:
        return "numeric"
    if normalized_role == "x" and visualization_id == "scatter":
        return "numeric"
    return ""


def normalize_field_type(value: str) -> str:
    normalized = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "floating": "float",
        "geographical": "geo",
        "geo_point": "geopoint",
        "geo_polygon": "geopolygon",
        "signed_integer": "integer",
        "unsigned_integer": "uint",
    }
    return aliases.get(normalized, normalized)
