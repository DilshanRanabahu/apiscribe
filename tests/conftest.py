"""Shared fixtures. HAR data is built in code and written to tmp_path; never commit real HAR files."""

import json

import pytest


def make_entry(
    url,
    method="GET",
    status=200,
    response_json=None,
    response_mime="application/json",
    response_text=None,
    request_json=None,
    request_headers=None,
):
    """Build one fake HAR entry. Pass response_text to control the raw body exactly."""
    if response_text is None and response_json is not None:
        response_text = json.dumps(response_json)

    request = {
        "method": method,
        "url": url,
        "headers": [{"name": k, "value": v} for k, v in (request_headers or {}).items()],
    }
    if request_json is not None:
        request["postData"] = {"mimeType": "application/json", "text": json.dumps(request_json)}

    content = {"mimeType": response_mime}
    if response_text is not None:
        content["text"] = response_text

    return {
        "request": request,
        "response": {"status": status, "headers": [], "content": content},
    }


def make_har(*entries):
    """Wrap entries in the top-level HAR structure."""
    return {"log": {"version": "1.2", "entries": list(entries)}}


@pytest.fixture
def write_har(tmp_path):
    """Write a HAR dict to a temp file and return its path."""

    def _write(har, name="traffic.har"):
        path = tmp_path / name
        path.write_text(json.dumps(har), encoding="utf-8")
        return path

    return _write
