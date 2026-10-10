import pytest

from apiscribe.schema import infer, infer_from_strings, merge, merge_all


# ---------- infer ----------

@pytest.mark.parametrize(
    "value, expected",
    [
        (True, {"type": "boolean"}),
        (3, {"type": "integer"}),
        (3.5, {"type": "number"}),
        ("hi", {"type": "string"}),
        (None, {"nullable": True}),
        ("2024-01-15T10:30:00Z", {"type": "string", "format": "date-time"}),
        ("2024-01-15T10:30:00.123+05:30", {"type": "string", "format": "date-time"}),
        ("2024-01-15", {"type": "string", "format": "date"}),
        ("3f2a9c1e-8b7d-4c6a-9e5f-1a2b3c4d5e6f", {"type": "string", "format": "uuid"}),
        ("bob@example.com", {"type": "string", "format": "email"}),
        ("https://example.com/a.png", {"type": "string", "format": "uri"}),
    ],
)
def test_infer_scalars(value, expected):
    assert infer(value) == expected


def test_infer_object_marks_all_keys_required():
    assert infer({"id": 1, "name": "a"}) == {
        "type": "object",
        "properties": {"id": {"type": "integer"}, "name": {"type": "string"}},
        "required": ["id", "name"],
    }


def test_infer_empty_object_and_array():
    assert infer({}) == {"type": "object", "properties": {}}
    assert infer([]) == {"type": "array", "items": {}}


def test_infer_array_merges_items():
    schema = infer([{"id": 1, "note": "x"}, {"id": 2}])
    assert schema == {
        "type": "array",
        "items": {
            "type": "object",
            "properties": {"id": {"type": "integer"}, "note": {"type": "string"}},
            "required": ["id"],
        },
    }


def test_infer_id_keyed_object_is_a_map():
    schema = infer({"42": {"qty": 1}, "57": {"qty": 2}})
    assert schema == {
        "type": "object",
        "additionalProperties": {"type": "object", "properties": {"qty": {"type": "integer"}}, "required": ["qty"]},
    }


# ---------- merge ----------

def test_required_vs_optional():
    merged = merge_all([infer({"id": 1, "total": 2.5, "note": "a"}), infer({"id": 2, "total": 3.0})])
    assert merged["required"] == ["id", "total"]
    assert set(merged["properties"]) == {"id", "total", "note"}


def test_property_never_required_if_missing_from_first_sample():
    merged = merge(infer({"id": 1}), infer({"id": 2, "extra": True}))
    assert merged["required"] == ["id"]
    assert merged["properties"]["extra"] == {"type": "boolean"}


def test_nullable():
    merged = merge_all([infer({"note": None}), infer({"note": "hi"})])
    assert merged["properties"]["note"] == {"type": "string", "nullable": True}
    assert merge(infer("hi"), infer(None)) == {"type": "string", "nullable": True}


def test_null_only_field_stays_untyped_nullable():
    assert merge(infer(None), infer(None)) == {"nullable": True}


def test_integer_and_number_widen():
    assert merge(infer(1), infer(1.5)) == {"type": "number"}
    assert merge(infer(1), infer(2)) == {"type": "integer"}


def test_string_format_dropped_if_samples_disagree():
    assert merge(infer("2024-01-15"), infer("2024-01-15")) == {"type": "string", "format": "date"}
    assert merge(infer("2024-01-15"), infer("hello")) == {"type": "string"}


def test_mixed_types_become_one_of():
    merged = merge_all([infer(1), infer("a"), infer(2.5), infer(None)])
    assert merged == {"oneOf": [{"type": "number"}, {"type": "string"}], "nullable": True}


def test_nested_objects_merge_recursively():
    a = infer({"customer": {"id": 1, "address": {"city": "X", "zip": "1"}}})
    b = infer({"customer": {"id": 2, "address": {"city": "Y"}}})
    address = merge(a, b)["properties"]["customer"]["properties"]["address"]
    assert address["required"] == ["city"]
    assert set(address["properties"]) == {"city", "zip"}


def test_empty_array_merges_with_filled_array():
    merged = merge(infer({"items": []}), infer({"items": [{"sku": "a"}]}))
    assert merged["properties"]["items"]["items"] == {
        "type": "object",
        "properties": {"sku": {"type": "string"}},
        "required": ["sku"],
    }


def test_no_empty_required_lists():
    merged = merge(infer({"a": 1}), infer({"b": 2}))
    assert "required" not in merged


def test_merge_does_not_mutate_inputs():
    a, b = infer({"id": 1}), infer({"id": 2.5, "x": None})
    a_copy, b_copy = repr(a), repr(b)
    merge(a, b)
    assert (repr(a), repr(b)) == (a_copy, b_copy)


def test_merge_all_empty():
    assert merge_all([]) is None


# ---------- strings from URLs ----------

@pytest.mark.parametrize(
    "values, expected",
    [
        (["1", "42"], {"type": "integer"}),
        (["1", "2.5"], {"type": "number"}),
        (["true", "False"], {"type": "boolean"}),
        (["3f2a9c1e-8b7d-4c6a-9e5f-1a2b3c4d5e6f"], {"type": "string", "format": "uuid"}),
        (["2024-01-15", "x"], {"type": "string"}),
        ([], {"type": "string"}),
    ],
)
def test_infer_from_strings(values, expected):
    assert infer_from_strings(values) == expected
