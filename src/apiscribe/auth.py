"""Detect the authentication scheme(s) used by requests.

Runs on the raw exchange (before redaction) because it needs to see e.g. whether a
Bearer token is a JWT. Only the scheme type and header/cookie/param *names* are kept,
never the values.
"""

from __future__ import annotations

import re

from apiscribe.har import Exchange

JWT_RE = re.compile(r"^eyJ[\w-]+\.[\w-]+\.[\w-]*$")
API_KEY_HEADER_RE = re.compile(r"^(x-)?(api[-_]?key|auth[-_]?token|access[-_]?token)$|^x-.*(api[-_]?key|token)$")
NOT_AUTH_HEADER_RE = re.compile(r"csrf|xsrf")
API_KEY_QUERY = {"api_key", "apikey", "api-key", "key", "access_token", "token", "auth", "auth_token"}
SESSION_COOKIE_RE = re.compile(r"sess|auth|token|jwt|(^|[._-])sid$", re.I)

Scheme = tuple[str, dict]


def detect(ex: Exchange) -> tuple[Scheme, ...]:
    """Return ((scheme_name, OpenAPI securityScheme), ...) for one request."""
    found: dict[str, dict] = {}
    headers = ex.request_headers

    authorization = headers.get("authorization", "").strip()
    if authorization:
        kind, _, credentials = authorization.partition(" ")
        kind = kind.lower()
        if kind == "bearer":
            scheme = {"type": "http", "scheme": "bearer"}
            if JWT_RE.match(credentials.strip()):
                scheme["bearerFormat"] = "JWT"
            found["bearerAuth"] = scheme
        elif kind == "basic":
            found["basicAuth"] = {"type": "http", "scheme": "basic"}
        else:  # e.g. "Token abc" or a bare key
            found["authorizationHeader"] = {"type": "apiKey", "in": "header", "name": "Authorization"}

    for name in headers:
        if name != "authorization" and API_KEY_HEADER_RE.match(name) and not NOT_AUTH_HEADER_RE.search(name):
            found[_scheme_name("header", name)] = {"type": "apiKey", "in": "header", "name": name}

    for name in ex.query:
        if name.lower() in API_KEY_QUERY:
            found[_scheme_name("query", name)] = {"type": "apiKey", "in": "query", "name": name}

    for part in headers.get("cookie", "").split(";"):
        name = part.partition("=")[0].strip()
        if name and SESSION_COOKIE_RE.search(name) and not NOT_AUTH_HEADER_RE.search(name.lower()):
            found[_scheme_name("cookie", name)] = {"type": "apiKey", "in": "cookie", "name": name}

    return tuple(sorted(found.items()))


def _scheme_name(location: str, name: str) -> str:
    """header + x-api-key -> headerXApiKey (valid as an OpenAPI component key)."""
    words = [w for w in re.split(r"[^A-Za-z0-9]+", name) if w]
    return location + "".join(w[:1].upper() + w[1:].lower() for w in words)
