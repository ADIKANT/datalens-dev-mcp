"""Stable plugin-owned input shapes; provider payloads remain extensible."""

STRING = {"type": "string", "minLength": 1}


def _dashboard_collection_change(*keys: str) -> dict:
    identity = {key: STRING for key in keys}
    return {
        "type": "object", "minProperties": 1, "additionalProperties": False,
        "properties": {
            "add": {"type": "array", "minItems": 1, "items": {
                "type": "object", "properties": identity, "required": list(keys)}},
            "update": {"type": "array", "minItems": 1, "items": {
                "type": "object", "properties": {**identity, "patch": {
                    "type": "object", "minProperties": 1,
                    "not": {"anyOf": [{"required": [key]} for key in keys]}}},
                "required": [*keys, "patch"], "additionalProperties": False}},
            "remove": {"type": "array", "minItems": 1, "uniqueItems": True,
                       "items": STRING if len(keys) == 1 else {
                           "type": "object", "properties": identity, "required": list(keys),
                           "additionalProperties": False}},
        },
    }


DASHBOARD_PATCH = {
    "type": "object", "properties": {"tabs": {
        "type": "array", "minItems": 1, "items": {
            "type": "object", "required": ["id"], "additionalProperties": False,
            "anyOf": [{"required": [key]} for key in ("patch", "items", "layout", "connections")],
            "properties": {
                "id": STRING,
                "patch": {"type": "object", "minProperties": 1, "additionalProperties": False,
                          "properties": {"title": STRING, "aliases": {"type": "object"},
                                         "settings": {"type": "object"}}},
                "items": _dashboard_collection_change("id"),
                "layout": _dashboard_collection_change("i"),
                "connections": _dashboard_collection_change("from", "to"),
            },
        },
    }},
    "required": ["tabs"], "additionalProperties": False,
}

TARGET = {
    "type": "object",
    "properties": {"object_type": STRING, "object_id": STRING,
                   "branch": {"enum": ["saved", "published"]}, "revision_id": STRING,
                   "expected_saved_revision": STRING},
    "required": ["object_type", "object_id"],
    "additionalProperties": False,
}
CHANGE = {
    "type": "object",
    "properties": {"object_type": STRING, "object_id": STRING, "expected_revision": STRING,
                   "patch": {"type": "object", "minProperties": 1}, "artifact_path": STRING,
                   "dashboard_patch": DASHBOARD_PATCH,
                   "remove_global_params": {"type": "array", "minItems": 1, "maxItems": 50,
                                            "uniqueItems": True, "items": STRING}},
    "required": ["object_type", "object_id"],
    "oneOf": [{"required": ["patch"]}, {"required": ["artifact_path"]},
              {"required": ["dashboard_patch", "expected_revision"],
               "properties": {"object_type": {"const": "dashboard"}}},
              {"required": ["remove_global_params", "expected_revision"],
               "properties": {"object_type": {"const": "dashboard"}}}],
    "dependentSchemas": {"dashboard_patch": {
        "required": ["expected_revision"],
        "properties": {"object_type": {"const": "dashboard"}, "patch": False,
                       "artifact_path": False, "remove_global_params": False}}},
    "additionalProperties": False,
}
FIELD = {
    "type": "object",
    "properties": {"guid": STRING, "title": {"type": "string"}, "name": {"type": "string"},
                   "formula": {"type": "string"}, "data_type": STRING, "aggregation": STRING},
    "required": ["guid"],
    "additionalProperties": True,
}
FILTER = {
    "type": "object",
    "properties": {"guid": STRING, "operation": STRING, "values": {"type": "array"}},
    "required": ["guid", "operation", "values"],
    "additionalProperties": True,
}
SORT = {"type": "object", "properties": {"guid": STRING, "direction": {"enum": ["asc", "desc"]}},
        "required": ["guid", "direction"], "additionalProperties": False}
PARAM = {"type": "object", "properties": {"guid": STRING, "value": {}},
         "required": ["guid", "value"], "additionalProperties": True}
DESTINATION = {"type": "object", "properties": {"workbook_id": STRING, "collection_id": STRING, "path": STRING},
               "oneOf": [{"required": [key]} for key in ("workbook_id", "collection_id", "path")],
               "additionalProperties": False}
DRAFT = {
    "type": "object",
    "properties": {"object_type": STRING, "artifact_path": STRING, "client_ref": STRING,
                   "depends_on": {"type": "array", "items": STRING}},
    "anyOf": [{"required": ["object_type"]}, {"required": ["artifact_path"]}],
    "additionalProperties": True,
}
READ_VIEW = {"type": "string", "enum": ["full", "summary", "projection"], "default": "full"}
READ_FIELDS = {"type": ["array", "null"], "minItems": 1,
               "items": {"type": "string", "pattern": "^/"}, "uniqueItems": True}
