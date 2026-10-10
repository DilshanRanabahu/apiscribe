from apiscribe.auth import detect
from tests.test_redact import JWT, make_exchange


def schemes(**overrides):
    return dict(detect(make_exchange(**overrides)))


def test_bearer_jwt():
    assert schemes(request_headers={"authorization": f"Bearer {JWT}"}) == {
        "bearerAuth": {"type": "http", "scheme": "bearer", "bearerFormat": "JWT"}
    }


def test_bearer_opaque_token():
    assert schemes(request_headers={"authorization": "Bearer abc123"}) == {
        "bearerAuth": {"type": "http", "scheme": "bearer"}
    }


def test_basic():
    assert schemes(request_headers={"authorization": "Basic dXNlcjpwYXNz"}) == {
        "basicAuth": {"type": "http", "scheme": "basic"}
    }


def test_other_authorization_scheme_is_api_key_header():
    assert schemes(request_headers={"authorization": "Token abc"}) == {
        "authorizationHeader": {"type": "apiKey", "in": "header", "name": "Authorization"}
    }


def test_api_key_header():
    assert schemes(request_headers={"x-api-key": "k"}) == {
        "headerXApiKey": {"type": "apiKey", "in": "header", "name": "x-api-key"}
    }


def test_api_key_query_param():
    assert schemes(query={"api_key": "k", "page": "1"}) == {
        "queryApiKey": {"type": "apiKey", "in": "query", "name": "api_key"}
    }


def test_session_cookie_only_name_kept():
    result = schemes(request_headers={"cookie": "theme=dark; sessionid=abc; _ga=GA1.2"})
    assert result == {"cookieSessionid": {"type": "apiKey", "in": "cookie", "name": "sessionid"}}


def test_csrf_is_not_auth():
    assert schemes(request_headers={"x-csrf-token": "t", "cookie": "csrftoken=t"}) == {}


def test_no_auth():
    assert schemes(request_headers={"accept": "application/json"}) == {}


def test_detect_returns_sorted_tuple():
    result = detect(make_exchange(request_headers={"authorization": "Basic x", "x-api-key": "k"}))
    assert [name for name, _ in result] == ["basicAuth", "headerXApiKey"]
