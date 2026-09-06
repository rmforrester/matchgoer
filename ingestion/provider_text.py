"""Decode one HTML character-reference layer in provider city/address text."""

import html
import re


_REFERENCE = re.compile(r"&(?:#[xX][0-9a-fA-F]+|#[0-9]+|[A-Za-z][A-Za-z0-9]+);")


def _decode_reference(match):
    token = match.group()
    if not token.startswith("&#") and token[1:] not in html.entities.html5:
        return token
    return html.unescape(token)


def has_decodable_references(value: str | None) -> bool:
    return value is not None and _REFERENCE.sub(_decode_reference, value) != value


def normalize_provider_text(value: str | None) -> str | None:
    """Return plain Unicode text, leaving unknown and ambiguous nested entities alone.

    Only complete references are decoded: ordinary ampersands and unknown names
    remain literal. Nested encodings are left for review rather than repeatedly
    decoded, making this single-layer boundary idempotent. This is not an HTML
    sanitizer; consumers must continue normal escaped/plain-text rendering.
    """
    if value is None:
        return None
    decoded = _REFERENCE.sub(_decode_reference, value)
    if has_decodable_references(decoded):
        return value
    return decoded
