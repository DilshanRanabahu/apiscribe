"""Mask sensitive data (tokens, cookies, passwords, emails) in exchanges.

Masking keeps the *shape* of the data (strings stay strings, numbers stay numbers),
so schemas can still be inferred, but the real values are gone. Every raw secret
seen is remembered in `Redactor.secrets` so the final output can be checked for leaks.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import replace
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from apiscribe.har import Exchange

REDACTED = "<redacted>"
REDACTED_EMAIL = "user@example.com"  # still a valid email, so the email format is kept

# Header values worth keeping: they describe the format, not the user.
SAFE_HEADERS = {"accept", "content-type"}
# Header names whose values are credentials.
SECRET_HEADER_RE = re.compile(r"authorization|cookie|token|api[-_]?key|secret|session|csrf|xsrf")

# Matched against the key lowercased with separators removed (so apiKey == api_key == api-key).
SENSITIVE_KEY_PARTS = (
    "password", "passwd", "secret", "token", "apikey", "accesskey", "privatekey",
    "session", "cookie", "credential", "authorization", "cardnumber", "creditcard",
    "signature",
)  # fmt: skip
SENSITIVE_KEYS_EXACT = {"auth", "pin", "otp", "cvv", "cvc", "ssn", "sig", "csrf", "xsrf"}

EMAIL_RE = re.compile(r"^[^@\s/]+@[^@\s/]+\.[A-Za-z]{2,}$")
JWT_RE = re.compile(r"^eyJ[\w-]+\.[\w-]+\.[\w-]*$")
UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I)
TOKEN_CHARS_RE = re.compile(r"^[A-Za-z0-9+/=_\-.~]+$")

MIN_SECRET_LEN = 8  # shorter values are too likely to appear in the output by coincidence


def is_sensitive_key(key: str) -> bool:
    norm = re.sub(r"[^a-z0-9]", "", key.lower())
    return norm in SENSITIVE_KEYS_EXACT or any(part in norm for part in SENSITIVE_KEY_PARTS)


def looks_secret(value: str) -> bool:
    """A JWT, or a long random-looking token. UUIDs are IDs, not secrets."""
    if JWT_RE.match(value):
        return True
    if len(value) < 24 or not TOKEN_CHARS_RE.match(value) or UUID_RE.match(value):
        return False
    has_letter = any(c.isalpha() for c in value)
    has_digit = any(c.isdigit() for c in value)
    return has_letter and has_digit and _entropy(value) >= 3.5


def _entropy(value: str) -> float:
    """Shannon entropy in bits per character; random tokens score high, words score low."""
    counts = Counter(value)
    return -sum(n / len(value) * math.log2(n / len(value)) for n in counts.values())


class Redactor:
    """Masks exchanges and remembers the raw secrets it removed."""

    def __init__(self) -> None:
        self.secrets: set[str] = set()

    def redact(self, ex: Exchange) -> Exchange:
        return replace(
            ex,
            path=self._path(ex.path),
            query={k: self._value(k, v) for k, v in ex.query.items()},
            request_headers=self._headers(ex.request_headers),
            response_headers=self._headers(ex.response_headers),
            request_body=self._value(None, ex.request_body),
            response_body=self._value(None, ex.response_body),
        )

    # ---------- headers ----------

    def _headers(self, headers: dict[str, str]) -> dict[str, str]:
        result = {}
        for name, value in headers.items():
            if name in SAFE_HEADERS:
                result[name] = value
                continue
            if SECRET_HEADER_RE.search(name):
                self._remember_header(name, value)
            result[name] = REDACTED
        return result

    def _remember_header(self, name: str, value: str) -> None:
        self._remember(value)
        if name == "authorization":
            self._remember(value.partition(" ")[2].strip())  # the token after "Bearer "
        elif name in ("cookie", "set-cookie"):
            parts = value.split(";") if name == "cookie" else value.split(";")[:1]
            for part in parts:
                self._remember(part.partition("=")[2].strip())

    # ---------- URL path ----------

    def _path(self, path: str) -> str:
        segments = []
        for seg in path.split("/"):
            if EMAIL_RE.match(seg) or looks_secret(seg):
                self._remember(seg)
                seg = REDACTED
            segments.append(seg)
        return "/".join(segments)

    # ---------- JSON values ----------

    def _value(self, key: str | None, value: Any, force: bool = False) -> Any:
        """Mask `value`. `force` means a parent key was sensitive, so mask every leaf."""
        force = force or (key is not None and is_sensitive_key(key))
        if isinstance(value, dict):
            return {self._key(k): self._value(k, v, force) for k, v in value.items()}
        if isinstance(value, list):
            return [self._value(key, v, force) for v in value]
        if isinstance(value, bool) or value is None:
            return value
        if isinstance(value, (int, float)):
            if force:
                self._remember(str(value))
                return type(value)(0)
            return value
        if isinstance(value, str):
            if force:
                self._remember(value)
                return REDACTED
            return self._string(value)
        return value

    def _key(self, key: str) -> str:
        """Object keys can hold data too, e.g. {"bob@example.com": {...}}."""
        if EMAIL_RE.match(key) or looks_secret(key):
            self._remember(key)
            return REDACTED
        return key

    def _string(self, value: str) -> str:
        if EMAIL_RE.match(value):
            self._remember(value)
            return REDACTED_EMAIL
        if looks_secret(value):
            self._remember(value)
            return REDACTED
        if value.startswith(("http://", "https://")):
            # Signed URLs carry tokens in the query string or user:pass@ in the host.
            parts = urlsplit(value)
            if parts.query or parts.username or parts.fragment:
                self._remember(value)
                host = parts.hostname or ""
                if parts.port:
                    host += f":{parts.port}"
                return urlunsplit((parts.scheme, host, parts.path, "", ""))
        return value

    def _remember(self, value: str) -> None:
        # Pure letters (e.g. "accepted") are too likely to clash with normal spec words.
        if len(value) >= MIN_SECRET_LEN and not value.isalpha():
            self.secrets.add(value)


def find_leaks(text: str, secrets: set[str]) -> list[str]:
    """Return the secrets that appear in `text`. Never print them; report the count."""
    return [secret for secret in secrets if secret in text]
