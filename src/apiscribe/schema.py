"""Infer JSON schemas (OpenAPI 3.0 style) from sample values and merge multiple samples.

Merge rules:
- a property is `required` only if it appeared in every sample
- a value that was ever null is `nullable`
- integer + number -> number
- different types -> oneOf
- objects whose keys are all IDs ({"42": {...}, "57": {...}}) -> additionalProperties
"""

from __future__ import annotations

import re
from functools import reduce
from typing import Any, Iterable

FORMATS = [
    ("date-time", re.compile(r"^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(:\d{2}(\.\d+)?)?(Z|[+-]\d{2}:?\d{2})?$")),
    ("date", re.compile(r"^\d{4}-\d{2}-\d{2}$")),
    ("uuid", re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I)),
    ("email", re.compile(r"^[^@\s/]+@[^@\s/]+\.[A-Za-z]{2,}$")),
    ("uri", re.compile(r"^https?://\S+$")),
]  # fmt: skip

INT_RE = re.compile(r"^-?\d+$")
FLOAT_RE = re.compile(r"^-?\d+\.\d+([eE][-+]?\d+)?$")
ID_KEY_RE = re.compile(r"^(-?\d+|[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})$", re.I)


def infer(value: Any) -> dict:
    """Schema for one JSON value."""
    if value is None:
        return {"nullable": True}
    if isinstance(value, bool):
        return {"type": "boolean"}
    if isinstance(value, int):
        return {"type": "integer"}
    if isinstance(value, float):
        return {"type": "number"}
    if isinstance(value, str):
        return _string_schema(_detect_format(value))
    if isinstance(value, list):
        return {"type": "array", "items": merge_all(infer(v) for v in value) or {}}
    if isinstance(value, dict):
        if value and all(ID_KEY_RE.match(k) for k in value):
            return {"type": "object", "additionalProperties": merge_all(infer(v) for v in value.values())}
        schema: dict = {"type": "object", "properties": {k: infer(v) for k, v in value.items()}}
        if value:
            schema["required"] = list(value)
        return schema
    return {}


def infer_from_strings(values: Iterable[str]) -> dict:
    """Schema for URL path/query values, which always arrive as strings."""
    values = list(values)
    if not values:
        return {"type": "string"}
    if all(INT_RE.match(v) for v in values):
        return {"type": "integer"}
    if all(INT_RE.match(v) or FLOAT_RE.match(v) for v in values):
        return {"type": "number"}
    if all(v.lower() in ("true", "false") for v in values):
        return {"type": "boolean"}
    formats = {_detect_format(v) for v in values}
    return _string_schema(formats.pop() if len(formats) == 1 else None)


def merge_all(schemas: Iterable[dict]) -> dict | None:
    """Merge many schemas into one; None if there were none."""
    schemas = list(schemas)
    return reduce(merge, schemas) if schemas else None


def merge(a: dict, b: dict) -> dict:
    """Merge two schemas into one that accepts both samples."""
    if a == b:
        return a
    nullable = a.get("nullable", False) or b.get("nullable", False)
    a, b = _without_nullable(a), _without_nullable(b)

    if not a:  # only null (or nothing) seen so far
        result = b
    elif not b:
        result = a
    else:
        result = _merge_typed(a, b)

    if nullable:
        result = {**result, "nullable": True}
    return result


def _merge_typed(a: dict, b: dict) -> dict:
    if "oneOf" in a or "oneOf" in b or _family(a) != _family(b):
        return _merge_one_of(a, b)

    kind = a["type"]
    if kind in ("integer", "number"):
        both_int = a["type"] == b["type"] == "integer"
        return {"type": "integer" if both_int else "number"}
    if kind == "string":
        return a if a.get("format") == b.get("format") else {"type": "string"}
    if kind == "array":
        return {"type": "array", "items": merge(a["items"], b["items"])}
    if kind == "object":
        return _merge_objects(a, b)
    return a  # boolean


def _merge_objects(a: dict, b: dict) -> dict:
    if "additionalProperties" in a or "additionalProperties" in b:
        values = merge(_value_schema(a), _value_schema(b))
        return {"type": "object", "additionalProperties": values}

    properties = dict(a["properties"])
    for key, schema in b["properties"].items():
        properties[key] = merge(properties[key], schema) if key in properties else schema

    b_required = set(b.get("required", []))
    required = [key for key in a.get("required", []) if key in b_required]

    result: dict = {"type": "object", "properties": properties}
    if required:  # OpenAPI 3.0 does not allow an empty required list
        result["required"] = required
    return result


def _value_schema(schema: dict) -> dict:
    """The schema of an object's values, for map-like objects."""
    if "additionalProperties" in schema:
        return schema["additionalProperties"]
    return merge_all(schema["properties"].values()) or {}


def _merge_one_of(a: dict, b: dict) -> dict:
    variants: list[dict] = []
    for schema in a.get("oneOf", [a]) + b.get("oneOf", [b]):
        for i, existing in enumerate(variants):
            if _family(existing) == _family(schema):
                variants[i] = merge(existing, schema)
                break
        else:
            variants.append(schema)
    return variants[0] if len(variants) == 1 else {"oneOf": variants}


def _family(schema: dict) -> str | None:
    kind = schema.get("type")
    return "number" if kind in ("integer", "number") else kind


def _without_nullable(schema: dict) -> dict:
    return {k: v for k, v in schema.items() if k != "nullable"}


def _detect_format(value: str) -> str | None:
    for name, pattern in FORMATS:
        if pattern.match(value):
            return name
    return None


def _string_schema(fmt: str | None) -> dict:
    return {"type": "string", "format": fmt} if fmt else {"type": "string"}
