import pytest

from apiscribe.paths import group_endpoints, is_id_segment, singularize
from apiscribe.redact import REDACTED
from tests.test_redact import make_exchange


def ex(path, method="GET", body=None, status=200):
    return make_exchange(method=method, path=path, response_body=body if body is not None else {"id": 1})


def summary(endpoints):
    return [(e.method, e.path) for e in endpoints]


@pytest.mark.parametrize(
    "segment",
    ["42", "0", "3f2a9c1e-8b7d-4c6a-9e5f-1a2b3c4d5e6f", "507f1f77bcf86cd799439011", "2024-01-15", "ord8f3k29x", REDACTED],
)
def test_id_segments(segment):
    assert is_id_segment(segment)


@pytest.mark.parametrize("segment", ["orders", "v2", "me", "oauth2", "api", "line-items", "base64"])
def test_static_segments(segment):
    assert not is_id_segment(segment)


@pytest.mark.parametrize(
    "word, expected",
    [("orders", "order"), ("categories", "category"), ("addresses", "address"),
     ("boxes", "box"), ("status", "status"), ("line-items", "line_item"), ("data", "data")],
)  # fmt: skip
def test_singularize(word, expected):
    assert singularize(word) == expected


def test_numeric_ids_grouped():
    endpoints = group_endpoints([ex("/orders/42"), ex("/orders/57")])
    assert summary(endpoints) == [("GET", "/orders/{order_id}")]
    assert endpoints[0].path_params == {"order_id": ["42", "57"]}
    assert len(endpoints[0].exchanges) == 2


def test_nested_ids():
    endpoints = group_endpoints([ex("/users/7/orders/42"), ex("/users/8/orders/43")])
    assert summary(endpoints) == [("GET", "/users/{user_id}/orders/{order_id}")]
    assert endpoints[0].path_params == {"user_id": ["7", "8"], "order_id": ["42", "43"]}


def test_consecutive_ids_get_unique_names():
    endpoints = group_endpoints([ex("/orders/42/99")])
    assert summary(endpoints) == [("GET", "/orders/{order_id}/{id}")]


def test_methods_are_separate_endpoints_sorted_by_path_then_method():
    endpoints = group_endpoints(
        [ex("/orders/1", "DELETE"), ex("/orders", "POST"), ex("/orders/2", "GET"), ex("/orders", "GET")]
    )
    assert summary(endpoints) == [
        ("GET", "/orders"),
        ("POST", "/orders"),
        ("GET", "/orders/{order_id}"),
        ("DELETE", "/orders/{order_id}"),
    ]


def test_static_neighbours_stay_static():
    endpoints = group_endpoints([ex("/users/me"), ex("/users/42"), ex("/v2/status")])
    assert summary(endpoints) == [("GET", "/users/me"), ("GET", "/users/{user_id}"), ("GET", "/v2/status")]


def test_trailing_slash_and_root():
    endpoints = group_endpoints([ex("/orders/"), ex("/orders"), ex("/")])
    assert summary(endpoints) == [("GET", "/"), ("GET", "/orders")]


def test_slugs_with_same_response_shape_are_merged():
    body = {"slug": "x", "name": "x", "price": 1}
    endpoints = group_endpoints(
        [ex("/products/red-shoe", body=body), ex("/products/blue-hat", body=body), ex("/products/green-bag", body=body)]
    )
    assert summary(endpoints) == [("GET", "/products/{product_id}")]
    assert endpoints[0].path_params == {"product_id": ["red-shoe", "blue-hat", "green-bag"]}


def test_sub_resources_with_different_shapes_are_not_merged():
    endpoints = group_endpoints(
        [
            ex("/users/1/orders", body=[{"id": 1}]),
            ex("/users/1/profile", body={"name": "a", "bio": "b"}),
            ex("/users/1/settings", body={"theme": "dark", "lang": "en"}),
        ]
    )
    assert summary(endpoints) == [
        ("GET", "/users/{user_id}/orders"),
        ("GET", "/users/{user_id}/profile"),
        ("GET", "/users/{user_id}/settings"),
    ]


def test_too_few_variants_are_not_merged():
    body = {"slug": "x"}
    endpoints = group_endpoints([ex("/products/red-shoe", body=body), ex("/products/blue-hat", body=body)])
    assert len(endpoints) == 2
