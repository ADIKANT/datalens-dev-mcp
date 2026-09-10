"""Stable plugin-owned input shapes; provider payloads remain extensible."""

STRING = {"type": "string", "minLength": 1}
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
                   "patch": {"type": "object", "minProperties": 1}, "artifact_path": STRING},
    "required": ["object_type", "object_id"],
    "oneOf": [{"required": ["patch"]}, {"required": ["artifact_path"]}],
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
