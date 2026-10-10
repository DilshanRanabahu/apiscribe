"""Load a HAR file and keep only JSON API calls as normalized exchanges."""

from __future__ import annotations

import base64
import binascii
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import SplitResult, parse_qsl, urlsplit


class HarError(Exception):
    """Raised when a HAR file cannot be read or has the wrong structure."""


@dataclass
class Exchange:
    """One request/response pair, cleaned up for the rest of the pipeline."""

    method: str
    base_url: str  # scheme://host[:port]
    host: str
    path: str
    query: dict[str, str]
    request_headers: dict[str, str]
    request_body: Any
    status: int
    response_headers: dict[str, str]
    response_body: Any
    # Filled in by auth.detect(): ((scheme_name, security_scheme), ...)
    security: tuple = ()


def load_har(path: Path) -> dict:
    """Read a HAR file from disk and check it has a `log.entries` list."""
    try:
        # utf-8-sig also handles files saved with a BOM
        data = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    except OSError as exc:
        raise HarError(f"Cannot read {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise HarError(f"{path} is not valid JSON: {exc}") from exc

    entries = data.get("log", {}).get("entries") if isinstance(data, dict) else None
    if not isinstance(entries, list):
        raise HarError(f"{path} is not a HAR file (missing log.entries)")
    return data


def extract_exchanges(har: dict, host: str) -> list[Exchange]:
    """Return the JSON API calls to `host`, skipping everything else."""
    exchanges = []
    for entry in har["log"]["entries"]:
        exchange = _to_exchange(entry, host)
        if exchange is not None:
            exchanges.append(exchange)
    return exchanges


def _to_exchange(entry: dict, host: str) -> Exchange | None:
    request = entry.get("request") or {}
    response = entry.get("response") or {}

    method = str(request.get("method", "")).upper()
    url = urlsplit(request.get("url", ""))
    status = response.get("status") or 0

    if not _host_matches(url, host):
        return None
    if method == "OPTIONS":  # CORS preflight, not a real API call
        return None
    if status <= 0:  # request blocked or failed, no real response
        return None

    post_data = request.get("postData") or {}
    request_body = _parse_json(post_data.get("text"), post_data.get("mimeType"))

    content = response.get("content") or {}
    response_body = _parse_json(
        content.get("text"), content.get("mimeType"), content.get("encoding")
    )

    # Keep the call if either side is JSON (e.g. POST with a JSON body -> 204 No Content)
    if request_body is None and response_body is None:
        return None

    return Exchange(
        method=method,
        base_url=f"{url.scheme}://{url.netloc.lower()}",
        host=url.hostname or "",
        path=url.path or "/",
        query=dict(parse_qsl(url.query, keep_blank_values=True)),
        request_headers=_headers(request.get("headers")),
        request_body=request_body,
        status=int(status),
        response_headers=_headers(response.get("headers")),
        response_body=response_body,
    )


def _host_matches(url: SplitResult, host: str) -> bool:
    """Match `api.example.com` against the hostname, or `host:port` against the netloc."""
    host = host.lower()
    return host in ((url.hostname or "").lower(), url.netloc.lower())


def _headers(raw: list | None) -> dict[str, str]:
    """HAR headers are a list of {name, value}; turn them into a dict with lowercase names."""
    return {str(h.get("name", "")).lower(): str(h.get("value", "")) for h in raw or []}


def _parse_json(text: str | None, mime_type: str | None, encoding: str | None = None) -> Any:
    """Return the parsed body, or None if it is missing or not JSON."""
    if not text or not _is_json_mime(mime_type):
        return None
    if encoding == "base64":
        try:
            text = base64.b64decode(text).decode("utf-8")
        except (binascii.Error, UnicodeDecodeError):
            return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def _is_json_mime(mime_type: str | None) -> bool:
    """True for application/json, application/problem+json, ...; ignores '; charset=...'."""
    if not mime_type:
        return False
    base = mime_type.split(";")[0].strip().lower()
    return base == "application/json" or base.endswith("+json")
