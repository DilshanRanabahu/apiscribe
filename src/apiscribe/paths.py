"""Group concrete URLs into templated endpoints, e.g. /orders/42 -> /orders/{order_id}.

Two passes:
1. Segments that look like IDs (numbers, UUIDs, hashes, ...) become parameters.
2. Static segments that vary at one position across many paths with similar
   responses (e.g. /products/red-shoe, /products/blue-hat) become parameters too.
"""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field

from apiscribe.har import Exchange
from apiscribe.redact import REDACTED

MIN_VARIANTS = 3  # distinct values needed before a static segment is treated as a parameter
MIN_SHAPE_SIMILARITY = 0.5  # shared top-level response keys / all keys

METHOD_ORDER = ["GET", "PUT", "POST", "DELETE", "OPTIONS", "HEAD", "PATCH", "TRACE"]

INT_RE = re.compile(r"^-?\d+$")
UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I)
HEX_RE = re.compile(r"^[0-9a-f]{12,}$", re.I)  # hashes, Mongo ObjectIds
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
ALNUM_RE = re.compile(r"^[A-Za-z0-9_-]+$")

Template = tuple[str, ...]


@dataclass
class Endpoint:
    method: str
    path: str  # e.g. /users/{user_id}/orders/{order_id}
    exchanges: list[Exchange] = field(default_factory=list)
    # Parameter name -> concrete values seen, in path order
    path_params: dict[str, list[str]] = field(default_factory=dict)


def is_id_segment(segment: str) -> bool:
    if segment == REDACTED:
        return True
    if INT_RE.match(segment) or UUID_RE.match(segment) or HEX_RE.match(segment):
        return True
    if DATE_RE.match(segment):
        return True
    # Mixed IDs like "ord8f3k29x"; needs several digits so words like "oauth2" stay static.
    digits = sum(c.isdigit() for c in segment)
    has_letter = any(c.isalpha() for c in segment)
    return bool(ALNUM_RE.match(segment)) and len(segment) >= 8 and has_letter and digits >= 3


def singularize(word: str) -> str:
    word = re.sub(r"[^a-z0-9]+", "_", word.lower()).strip("_")
    if word.endswith("ies") and len(word) > 4:
        return word[:-3] + "y"
    if word.endswith(("sses", "xes", "ches", "shes")):
        return word[:-2]
    if word.endswith("s") and not word.endswith(("ss", "us", "is")):
        return word[:-1]
    return word


def group_endpoints(exchanges: list[Exchange], min_variants: int = MIN_VARIANTS) -> list[Endpoint]:
    """Group exchanges by (method, templated path), sorted by path then method."""
    templates = [_template(_split(ex.path)) for ex in exchanges]
    mapping = _merge_variable_segments(exchanges, templates, min_variants)

    endpoints: dict[tuple[str, str], Endpoint] = {}
    for ex, template in zip(exchanges, templates):
        final = mapping[template]
        path = "/" + "/".join(final)
        endpoint = endpoints.setdefault((ex.method, path), Endpoint(ex.method, path))
        endpoint.exchanges.append(ex)
        for segment, value in zip(final, _split(ex.path)):
            if _is_param(segment):
                endpoint.path_params.setdefault(segment[1:-1], []).append(value)

    return sorted(endpoints.values(), key=lambda e: (e.path, _method_rank(e.method)))


def _split(path: str) -> list[str]:
    return [s for s in path.split("/") if s]


def _is_param(segment: str) -> bool:
    return segment.startswith("{") and segment.endswith("}")


def _method_rank(method: str) -> int:
    return METHOD_ORDER.index(method) if method in METHOD_ORDER else len(METHOD_ORDER)


def _param_name(previous: str | None, used: set[str]) -> str:
    """Name a parameter after the segment before it: orders -> order_id."""
    base = f"{singularize(previous)}_id" if previous and not _is_param(previous) else "id"
    name, n = base, 2
    while name in used:
        name, n = f"{base}{n}", n + 1
    used.add(name)
    return name


def _template(segments: list[str]) -> Template:
    used: set[str] = set()
    result = []
    for i, segment in enumerate(segments):
        if is_id_segment(segment):
            previous = result[i - 1] if i > 0 else None
            segment = "{" + _param_name(previous, used) + "}"
        result.append(segment)
    return tuple(result)


def _merge_variable_segments(
    exchanges: list[Exchange], templates: list[Template], min_variants: int
) -> dict[Template, Template]:
    """Second pass: turn a static position into a parameter when it varies a lot."""
    shapes: dict[Template, list] = defaultdict(list)
    for ex, template in zip(exchanges, templates):
        if 200 <= ex.status < 300 and ex.response_body is not None:
            shapes[template].append(_shape(ex.response_body))

    mapping = {t: t for t in templates}
    while True:
        current = set(mapping.values())
        buckets: dict[tuple[Template, Template], set[str]] = defaultdict(set)
        for t in current:
            for i, segment in enumerate(t):
                if not _is_param(segment):
                    buckets[(t[:i], t[i + 1 :])].add(segment)

        target = None
        for (prefix, suffix), values in sorted(buckets.items()):
            if len(values) < min_variants:
                continue
            members = [prefix + (v,) + suffix for v in values]
            member_shapes = [[s for o, m in mapping.items() if m == t for s in shapes[o]] for t in members]
            if _similar(member_shapes):
                target = prefix, suffix, values
                break
        if target is None:
            return mapping

        prefix, suffix, values = target
        used = {s[1:-1] for s in prefix + suffix if _is_param(s)}
        previous = prefix[-1] if prefix else None
        merged = prefix + ("{" + _param_name(previous, used) + "}",) + suffix
        for original, cur in mapping.items():
            if (
                len(cur) == len(merged)
                and cur[: len(prefix)] == prefix
                and cur[len(prefix) + 1 :] == suffix
                and cur[len(prefix)] in values
            ):
                mapping[original] = merged


def _shape(body) -> object:
    return frozenset(body) if isinstance(body, dict) else type(body).__name__


def _similar(member_shapes: list[list]) -> bool:
    """True if every candidate has responses and they share most top-level keys."""
    if any(not shapes for shapes in member_shapes):
        return False  # no evidence: keep the paths separate
    flat = [s for shapes in member_shapes for s in shapes]
    if all(isinstance(s, frozenset) for s in flat):
        union = frozenset().union(*flat)
        common = frozenset.intersection(*flat)
        return not union or len(common) / len(union) >= MIN_SHAPE_SIMILARITY
    return len(set(flat)) == 1
