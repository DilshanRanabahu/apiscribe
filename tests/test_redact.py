from apiscribe.har import Exchange
from apiscribe.redact import REDACTED, REDACTED_EMAIL, Redactor, find_leaks, is_sensitive_key, looks_secret

JWT = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U"
OPAQUE_TOKEN = "faketok9fQ2xLk8Zr4Tq1Vb7Nw3Hy6Pm5"


def make_exchange(**overrides) -> Exchange:
    fields = dict(
        method="GET",
        base_url="https://api.example.com",
        host="api.example.com",
        path="/orders/42",
        query={},
        request_headers={},
        request_body=None,
        status=200,
        response_headers={},
        response_body=None,
    )
    fields.update(overrides)
    return Exchange(**fields)


# ---------- helpers ----------

def test_sensitive_keys():
    for key in ["password", "newPassword", "access_token", "apiKey", "API-KEY", "client_secret", "sessionId", "pin"]:
        assert is_sensitive_key(key), key
    for key in ["id", "name", "total", "classname", "author", "spinner", "keyboard"]:
        assert not is_sensitive_key(key), key


def test_looks_secret():
    assert looks_secret(JWT)
    assert looks_secret(OPAQUE_TOKEN)
    assert not looks_secret("3f2a9c1e-8b7d-4c6a-9e5f-1a2b3c4d5e6f")  # UUID is an ID
    assert not looks_secret("hello world")
    assert not looks_secret("short1")
    assert not looks_secret("2024-01-15T10:30:00Z")


# ---------- headers ----------

def test_auth_and_cookie_headers_are_masked_and_remembered():
    r = Redactor()
    ex = r.redact(
        make_exchange(
            request_headers={
                "authorization": f"Bearer {OPAQUE_TOKEN}",
                "cookie": "sessionid=abc123def456; theme=dark",
                "content-type": "application/json",
                "user-agent": "Mozilla/5.0",
            }
        )
    )
    assert ex.request_headers["authorization"] == REDACTED
    assert ex.request_headers["cookie"] == REDACTED
    assert ex.request_headers["user-agent"] == REDACTED
    assert ex.request_headers["content-type"] == "application/json"
    assert OPAQUE_TOKEN in r.secrets
    assert "abc123def456" in r.secrets


def test_set_cookie_response_header_is_masked():
    r = Redactor()
    ex = r.redact(make_exchange(response_headers={"set-cookie": "sid=s3cr3tValue99; Path=/; HttpOnly"}))
    assert ex.response_headers["set-cookie"] == REDACTED
    assert "s3cr3tValue99" in r.secrets


# ---------- bodies ----------

def test_sensitive_keys_masked_but_type_kept():
    r = Redactor()
    ex = r.redact(
        make_exchange(request_body={"username": "alice", "password": "hunter2!!", "pin": 1234, "remember": True})
    )
    assert ex.request_body == {"username": "alice", "password": REDACTED, "pin": 0, "remember": True}
    assert "hunter2!!" in r.secrets


def test_everything_under_a_sensitive_key_is_masked():
    r = Redactor()
    body = {"credentials": {"user": "alice", "keys": ["k1-abcdefgh", "k2-abcdefgh"], "ttl": 3600}}
    ex = r.redact(make_exchange(response_body=body))
    assert ex.response_body == {"credentials": {"user": REDACTED, "keys": [REDACTED, REDACTED], "ttl": 0}}


def test_emails_and_tokens_masked_by_value():
    r = Redactor()
    body = {"contact": "bob@example.org", "note": JWT, "items": [{"ref": OPAQUE_TOKEN}]}
    ex = r.redact(make_exchange(response_body=body))
    assert ex.response_body == {"contact": REDACTED_EMAIL, "note": REDACTED, "items": [{"ref": REDACTED}]}
    assert {"bob@example.org", JWT, OPAQUE_TOKEN} <= r.secrets


def test_normal_values_untouched():
    body = {"id": 42, "name": "Alice", "price": 9.5, "id2": "3f2a9c1e-8b7d-4c6a-9e5f-1a2b3c4d5e6f", "tags": ["a"]}
    ex = Redactor().redact(make_exchange(response_body=body))
    assert ex.response_body == body


def test_signed_url_query_stripped():
    r = Redactor()
    url = "https://cdn.example.com/file.pdf?X-Amz-Signature=abcdef123456"
    ex = r.redact(make_exchange(response_body={"download": url}))
    assert ex.response_body == {"download": "https://cdn.example.com/file.pdf"}


def test_email_object_keys_masked():
    r = Redactor()
    ex = r.redact(make_exchange(response_body={"bob@example.org": {"role": "admin"}}))
    assert ex.response_body == {REDACTED: {"role": "admin"}}


# ---------- URL ----------

def test_query_params_masked():
    r = Redactor()
    ex = r.redact(make_exchange(query={"api_key": "key-1234567", "page": "2", "email": "a@b.co"}))
    assert ex.query == {"api_key": REDACTED, "page": "2", "email": REDACTED_EMAIL}


def test_sensitive_path_segments_masked():
    r = Redactor()
    ex = r.redact(make_exchange(path=f"/users/bob@example.org/reset/{OPAQUE_TOKEN}"))
    assert ex.path == f"/users/{REDACTED}/reset/{REDACTED}"
    assert OPAQUE_TOKEN in r.secrets


# ---------- leak check ----------

def test_find_leaks():
    assert find_leaks("openapi: 3.0.3\ntoken: abc123def456\n", {"abc123def456"}) == ["abc123def456"]
    assert find_leaks("openapi: 3.0.3\n", {"abc123def456"}) == []


def test_short_or_plain_word_values_not_remembered():
    r = Redactor()
    r.redact(make_exchange(request_headers={"cookie": "session=yes; auth=accepted"}))
    assert r.secrets == {"session=yes; auth=accepted"}
