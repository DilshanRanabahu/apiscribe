from dataclasses import replace

import yaml
from openapi_spec_validator import validate

from apiscribe.auth import detect
from apiscribe.openapi import build, to_yaml
from apiscribe.paths import group_endpoints
from tests.test_redact import make_exchange


def spec_for(*exchanges, title="Test API"):
    exchanges = [replace(ex, security=detect(ex)) for ex in exchanges]
    return build(group_endpoints(exchanges), title=title)


def test_minimal_spec_is_valid():
    spec = spec_for(make_exchange(path="/orders/42", response_body={"id": 42}))
    validate(spec)
    assert spec["openapi"] == "3.0.3"
    assert spec["info"]["title"] == "Test API"
    assert spec["servers"] == [{"url": "https://api.example.com"}]


def test_operation_parameters_and_responses():
    spec = spec_for(
        make_exchange(path="/orders/42", query={"expand": "items"}, response_body={"id": 42, "note": None}),
        make_exchange(path="/orders/57", response_body={"id": 57, "note": "hi"}),
        make_exchange(path="/orders/99", status=404, response_body={"error": "not found"}),
    )
    validate(spec)
    op = spec["paths"]["/orders/{order_id}"]["get"]
    assert op["operationId"] == "getOrdersByOrderId"
    assert op["tags"] == ["orders"]
    assert op["parameters"] == [
        {"name": "order_id", "in": "path", "required": True, "schema": {"type": "integer"}},
        {"name": "expand", "in": "query", "required": False, "schema": {"type": "string"}},
    ]
    ok = op["responses"]["200"]
    assert ok["description"] == "OK"
    assert ok["content"]["application/json"]["schema"] == {
        "type": "object",
        "properties": {"id": {"type": "integer"}, "note": {"type": "string", "nullable": True}},
        "required": ["id", "note"],
    }
    assert op["responses"]["404"]["description"] == "Not Found"


def test_request_body_and_empty_response():
    spec = spec_for(
        make_exchange(method="POST", path="/orders", status=201, request_body={"sku": "a", "qty": 1},
                      response_body={"id": 1}),
        make_exchange(method="POST", path="/orders", status=204, request_body={"sku": "b"}),
    )  # fmt: skip
    validate(spec)
    op = spec["paths"]["/orders"]["post"]
    assert op["requestBody"]["required"] is True
    assert op["requestBody"]["content"]["application/json"]["schema"]["required"] == ["sku"]
    assert op["responses"]["204"] == {"description": "No Content"}


def test_security_schemes():
    spec = spec_for(
        make_exchange(path="/me", request_headers={"authorization": "Bearer abc"}, response_body={}),
        make_exchange(path="/health", response_body={"ok": True}),
    )
    validate(spec)
    assert spec["components"]["securitySchemes"] == {"bearerAuth": {"type": "http", "scheme": "bearer"}}
    assert spec["paths"]["/me"]["get"]["security"] == [{"bearerAuth": []}]
    assert "security" not in spec["paths"]["/health"]["get"]


def test_auth_optional_when_some_calls_lack_it():
    spec = spec_for(
        make_exchange(path="/feed", request_headers={"authorization": "Bearer abc"}, response_body=[]),
        make_exchange(path="/feed", response_body=[]),
    )
    assert spec["paths"]["/feed"]["get"]["security"] == [{"bearerAuth": []}, {}]


def test_no_components_without_auth():
    assert "components" not in spec_for(make_exchange(response_body={}))


def test_operation_ids_unique_and_root():
    spec = spec_for(make_exchange(path="/", response_body={}), make_exchange(path="/api/v1/users", response_body=[]))
    assert spec["paths"]["/"]["get"]["operationId"] == "getRoot"
    assert spec["paths"]["/api/v1/users"]["get"]["operationId"] == "getApiV1Users"
    assert spec["paths"]["/api/v1/users"]["get"]["tags"] == ["users"]
    assert "tags" not in spec["paths"]["/"]["get"]


def test_yaml_round_trips_without_anchors():
    shared = {"id": 1, "tags": ["a"]}
    spec = spec_for(make_exchange(response_body={"a": shared, "b": shared, "list": [shared, shared]}))
    text = to_yaml(spec)
    assert "&id" not in text and "*id" not in text
    assert yaml.safe_load(text) == spec
    validate(yaml.safe_load(text))


def test_output_is_deterministic():
    exchanges = [make_exchange(path=f"/orders/{i}", response_body={"id": i}) for i in range(5)]
    assert to_yaml(spec_for(*exchanges)) == to_yaml(spec_for(*exchanges))
