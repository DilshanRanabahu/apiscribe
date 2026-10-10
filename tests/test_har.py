import base64
import json

import pytest

from apiscribe.har import HarError, extract_exchanges, load_har
from tests.conftest import make_entry, make_har

HOST = "api.example.com"


# ---------- load_har ----------

def test_load_har_reads_valid_file(write_har):
    path = write_har(make_har(make_entry(f"https://{HOST}/orders/1", response_json={"id": 1})))
    assert len(load_har(path)["log"]["entries"]) == 1


def test_load_har_rejects_invalid_json(tmp_path):
    path = tmp_path / "bad.har"
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(HarError, match="not valid JSON"):
        load_har(path)


def test_load_har_rejects_json_without_entries(write_har):
    path = write_har({"hello": "world"})
    with pytest.raises(HarError, match="missing log.entries"):
        load_har(path)


def test_load_har_missing_file(tmp_path):
    with pytest.raises(HarError, match="Cannot read"):
        load_har(tmp_path / "nope.har")


# ---------- extract_exchanges: what we keep ----------

def test_keeps_json_call_and_normalizes_it():
    har = make_har(
        make_entry(
            f"https://{HOST}/orders/42?expand=items&page=2",
            response_json={"id": 42},
            request_headers={"Authorization": "Bearer abc"},
        )
    )
    [ex] = extract_exchanges(har, HOST)
    assert ex.method == "GET"
    assert ex.base_url == f"https://{HOST}"
    assert ex.host == HOST
    assert ex.path == "/orders/42"
    assert ex.query == {"expand": "items", "page": "2"}
    assert ex.request_headers == {"authorization": "Bearer abc"}  # names lowercased
    assert ex.status == 200
    assert ex.response_body == {"id": 42}


def test_keeps_json_mime_with_charset_and_plus_json():
    har = make_har(
        make_entry(f"https://{HOST}/a", response_json=[], response_mime="application/json; charset=utf-8"),
        make_entry(f"https://{HOST}/b", response_json={}, response_mime="application/problem+json"),
    )
    assert [ex.path for ex in extract_exchanges(har, HOST)] == ["/a", "/b"]


def test_decodes_base64_body():
    encoded = base64.b64encode(json.dumps({"ok": True}).encode()).decode()
    entry = make_entry(f"https://{HOST}/status", response_text=encoded)
    entry["response"]["content"]["encoding"] = "base64"
    [ex] = extract_exchanges(make_har(entry), HOST)
    assert ex.response_body == {"ok": True}


def test_keeps_post_with_json_request_and_empty_response():
    har = make_har(
        make_entry(f"https://{HOST}/orders", method="POST", status=204,
                   request_json={"item": "book"}, response_mime="")
    )
    [ex] = extract_exchanges(har, HOST)
    assert ex.request_body == {"item": "book"}
    assert ex.response_body is None


def test_host_match_is_case_insensitive_and_supports_port():
    har = make_har(make_entry("https://API.Example.com:8443/x", response_json={}))
    assert len(extract_exchanges(har, HOST)) == 1
    assert len(extract_exchanges(har, "api.example.com:8443")) == 1


# ---------- extract_exchanges: what we drop ----------

def test_drops_other_hosts():
    har = make_har(make_entry("https://cdn.example.com/x", response_json={}))
    assert extract_exchanges(har, HOST) == []


def test_drops_non_json_responses():
    har = make_har(
        make_entry(f"https://{HOST}/logo.png", response_mime="image/png", response_text="binary"),
        make_entry(f"https://{HOST}/", response_mime="text/html", response_text="<html></html>"),
    )
    assert extract_exchanges(har, HOST) == []


def test_drops_invalid_json_body():
    har = make_har(make_entry(f"https://{HOST}/x", response_text="{broken"))
    assert extract_exchanges(har, HOST) == []


def test_drops_options_preflight():
    har = make_har(make_entry(f"https://{HOST}/x", method="OPTIONS", response_json={}))
    assert extract_exchanges(har, HOST) == []


def test_drops_failed_requests_with_status_zero():
    har = make_har(make_entry(f"https://{HOST}/x", status=0, response_json={}))
    assert extract_exchanges(har, HOST) == []


def test_keeps_error_responses():
    har = make_har(make_entry(f"https://{HOST}/x", status=404, response_json={"error": "not found"}))
    [ex] = extract_exchanges(har, HOST)
    assert ex.status == 404
