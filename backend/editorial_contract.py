"""Deterministic checks supporting Matchgoer's human editorial contract.

This module intentionally detects only mechanical omissions and known filler
patterns.  It does not attempt to decide whether prose is interesting or useful.
"""

from __future__ import annotations

import re
from collections import Counter


STANDARD_VERSION = "2026-09-22"
VALUE_ROUTES = {"DECISION", "UNDERSTANDING_EXPERIENCE", "PRACTICAL"}
REQUIRED_REVIEW_FIELDS = {
    "value_route",
    "why_matchgoer_cares",
    "disappearance_loss",
    "ui_duplicate",
    "know_duplicate",
    "btm_duplicate",
    "decide_duplicate",
    "editorial_standard_version",
}

FAIL_PATTERNS = {
    "generic_ticket_routing": re.compile(
        r"\b(use|visit|consult|check) (the )?(official )?(ticket|tickets|ticketing)"
        r"|\bofficial (ticket|ticketing) (page|site|website|route|directory)\b",
        re.I,
    ),
    "check_confirm_filler": re.compile(
        r"\b(confirm|check|consult) (the )?(current |latest )?"
        r"(venue|kickoff|arrangements|details|guidance).{0,35}(before (you )?travel|before travel|matchday)\b",
        re.I,
    ),
    "venue_is_home": re.compile(
        r"\b(is|remains|serves as) (the )?(club'?s|team'?s|their) "
        r"(canonical |current |regular )?(home )?(ground|stadium|venue)\b",
        re.I,
    ),
}

FLAG_PATTERNS = {
    "generic_community_mission": re.compile(r"\bcommunity[- ]focused|serves the community|community mission\b", re.I),
    "generic_development_claim": re.compile(r"\bdevelopment (programme|program|pathway)|developing players\b", re.I),
    "generic_supporter_group": re.compile(r"\bsupporters? (group|club).{0,30}(supports?|backs?|follows?)\b", re.I),
    "vague_transport": re.compile(r"\b(public transport|transit options|transport options) (is|are) available\b", re.I),
}


class EditorialContractError(ValueError):
    """Raised when a deterministic editorial gate fails."""


def normalize_text(value: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9]+", " ", value.lower()).split())


def validate_review_metadata(review: dict) -> None:
    missing = sorted(REQUIRED_REVIEW_FIELDS - set(review))
    if missing:
        raise EditorialContractError(f"missing editorial review fields: {', '.join(missing)}")
    if review["editorial_standard_version"] != STANDARD_VERSION:
        raise EditorialContractError("unsupported editorial standard version")
    if review["value_route"] not in VALUE_ROUTES:
        raise EditorialContractError("invalid value route")
    for field in ("why_matchgoer_cares", "disappearance_loss"):
        if not isinstance(review[field], str) or not review[field].strip():
            raise EditorialContractError(f"{field} must be substantive")
    for field in ("ui_duplicate", "know_duplicate", "btm_duplicate", "decide_duplicate"):
        if not isinstance(review[field], bool):
            raise EditorialContractError(f"{field} must be boolean")


def inspect_text(text: str) -> dict[str, list[str]]:
    return {
        "fails": [name for name, pattern in FAIL_PATTERNS.items() if pattern.search(text)],
        "flags": [name for name, pattern in FLAG_PATTERNS.items() if pattern.search(text)],
    }


def inspect_page(facts: list[dict], btm_lines: list[str] | None = None) -> dict:
    """Return deterministic failures and human-review flags for an assembled page."""
    failures: list[dict] = []
    flags: list[dict] = []
    normalized: list[str] = []
    btm = {normalize_text(value) for value in (btm_lines or []) if normalize_text(value)}

    for index, fact in enumerate(facts):
        review = fact.get("editorial_review")
        try:
            validate_review_metadata(review if isinstance(review, dict) else {})
        except EditorialContractError as exc:
            failures.append({"index": index, "code": "editorial_metadata", "detail": str(exc)})
        text = " ".join(str(fact.get(key) or "") for key in ("headline", "content")).strip()
        result = inspect_text(text)
        failures.extend({"index": index, "code": code} for code in result["fails"])
        flags.extend({"index": index, "code": code} for code in result["flags"])
        norm = normalize_text(text)
        normalized.append(norm)
        if norm and norm in btm:
            failures.append({"index": index, "code": "exact_btm_duplicate"})

    duplicate_text = {text for text, count in Counter(normalized).items() if text and count > 1}
    for index, text in enumerate(normalized):
        if text in duplicate_text:
            failures.append({"index": index, "code": "exact_know_duplicate"})

    return {"result": "FAIL" if failures else "PASS", "failures": failures, "flags": flags}

