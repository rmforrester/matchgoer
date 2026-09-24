"""Deterministic checks supporting Matchgoer's human editorial contract.

This module intentionally detects only mechanical omissions and known filler
patterns.  It does not attempt to decide whether prose is interesting or useful.
"""

from __future__ import annotations

import re
from collections import Counter


STANDARD_VERSION = "2026-09-24"
VALUE_ROUTES = {"DECISION", "UNDERSTANDING_EXPERIENCE", "PRACTICAL"}
CONTEXT_LEVELS = {"COUNTRY", "PYRAMID", "REGION", "COMPETITION_LEVEL", "CLUB_GROUND_SUPPORTERS"}
FIRST_PASS_READY = "FIRST_PASS_READY_FOR_HUMAN_REVIEW"
LANGUAGE_STRENGTH_LEVELS = {"A", "B", "C", "D"}
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
    "editorial_rubric_leakage": re.compile(
        r"\b(changes? fixture choice|affects? fixture selection|materially affects? selection|"
        r"contextual(?:ly)? significant|peer[- ]normalised|supporter salience|"
        r"material travelling support|passes? the threshold|evidence beyond age alone|"
        r"qualifies because|category[- ]fit|approval criteria|disappearance test|"
        r"relative distinction|editorial standard|evidence threshold)\b",
        re.I,
    ),
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
    "unsupported_colour_requires_evidence": re.compile(
        r"\b(electric atmosphere|incredible fans?|hostile ground|bouncing terrace|"
        r"unforgettable night|legendary support|passionate fanbase)\b",
        re.I,
    ),
    "generic_community_mission": re.compile(r"\bcommunity[- ]focused|serves the community|community mission\b", re.I),
    "generic_development_claim": re.compile(r"\bdevelopment (programme|program|pathway)|developing players\b", re.I),
    "generic_supporter_group": re.compile(r"\bsupporters? (group|club).{0,30}(supports?|backs?|follows?)\b", re.I),
    "vague_transport": re.compile(r"\b(public transport|transit options|transport options) (is|are) available\b", re.I),
}


class EditorialContractError(ValueError):
    """Raised when a deterministic editorial gate fails."""


def validate_contextual_significance(context: dict) -> None:
    """Validate audit metadata for a contextual DECIDE adjudication.

    This validates that contextual reasoning happened; it never decides that a
    candidate is significant.
    """
    required = {"country", "context_level", "context_rationale", "supporter_value", "relative_distinction_only"}
    missing = sorted(required - set(context))
    if missing:
        raise EditorialContractError(f"missing significance context fields: {', '.join(missing)}")
    if context["context_level"] not in CONTEXT_LEVELS:
        raise EditorialContractError("invalid significance context level")
    for field in ("country", "context_rationale", "supporter_value"):
        if not isinstance(context[field], str) or not context[field].strip():
            raise EditorialContractError(f"{field} must be substantive")
    if not isinstance(context["relative_distinction_only"], bool):
        raise EditorialContractError("relative_distinction_only must be boolean")
    if context["relative_distinction_only"]:
        raise EditorialContractError("relative significance alone cannot qualify content")


def validate_first_pass_capture(capture: dict) -> None:
    """Require deliberate research coverage; published outcomes may remain zero."""
    for area in ("club", "supporters", "matchday", "btm", "decide", "tickets", "directions"):
        item = capture.get(area)
        if not isinstance(item, dict) or item.get("assessed") is not True:
            raise EditorialContractError(f"first pass did not deliberately assess {area}")
        if item.get("outcome") not in {"PUBLISH", "DELIBERATE_ZERO", "NOT_APPLICABLE"}:
            raise EditorialContractError(f"first-pass {area} outcome is invalid")


def validate_tone_review(review: dict) -> None:
    """Validate mechanical tone-review metadata without judging prose quality."""
    if review.get("actual_supporter_copy_reviewed") is not True:
        raise EditorialContractError("first pass did not review actual supporter-facing copy")
    if review.get("rendered_hierarchy_reviewed") is not True:
        raise EditorialContractError("first pass did not review rendered hierarchy")
    levels = review.get("language_strength_levels")
    if not isinstance(levels, list) or not levels:
        raise EditorialContractError("first pass must record language-strength levels")
    if any(level not in LANGUAGE_STRENGTH_LEVELS for level in levels):
        raise EditorialContractError("invalid language-strength level")
    if review.get("level_c_d_reviewed") is not True:
        raise EditorialContractError("Level C/D recommendations require explicit first-pass review")


def validate_language_strength(level: str, human_approval: dict | None = None) -> None:
    if level not in LANGUAGE_STRENGTH_LEVELS:
        raise EditorialContractError("invalid language-strength level")
    if level == "D":
        approval = human_approval or {}
        if approval.get("approved") is not True or str(approval.get("reviewed_by") or "").strip().lower() not in {"ray", "ray/assistant"}:
            raise EditorialContractError("Level D requires explicit human approval from Ray")
        if not str(approval.get("approved_at") or "").strip():
            raise EditorialContractError("Level D approval timestamp is required")


def validate_ticket_copy_ownership(copy: dict) -> None:
    """Prevent MATCHDAY prose from duplicating an eligible fixture Buy Tickets CTA."""
    if not isinstance(copy.get("fixture_buy_tickets_cta_present"), bool):
        raise EditorialContractError("ticket-copy review must record fixture CTA presence")
    if not isinstance(copy.get("non_obvious_exception"), bool):
        raise EditorialContractError("ticket-copy review must record whether an exception exists")
    if copy["fixture_buy_tickets_cta_present"] and copy.get("ordinary_purchase_instruction_retained") is True:
        raise EditorialContractError("ordinary ticket-purchase prose duplicates the fixture CTA")


def validate_voice_collection(items: list[dict]) -> None:
    """Reject obvious bulk-template repetition; human review still judges naturalness."""
    openings = {
        "if_you_like": re.compile(r"^if you (like|love|want)\b", re.I),
        "head_to": re.compile(r"^head to\b", re.I),
        "more_than": re.compile(r"^.+?\bis more than\b", re.I),
    }
    counts = Counter()
    for item in items:
        value = str(item.get("copy") or "").strip()
        for name, pattern in openings.items():
            if pattern.search(value):
                counts[name] += 1
    repeated = sorted(name for name, count in counts.items() if count >= 3)
    if repeated:
        raise EditorialContractError(f"formulaic copy pattern repeated: {', '.join(repeated)}")


def validate_bulk_country_gate(gate: dict) -> None:
    """Fail closed unless the mandatory human product/editorial gate passed."""
    if gate.get("country_context_calibrated") is not True:
        raise EditorialContractError("country context calibration is incomplete")
    if gate.get("decide_landscape_calibrated") is not True:
        raise EditorialContractError("DECIDE landscape calibration is incomplete")
    if gate.get("representative_first_pass_status") != FIRST_PASS_READY:
        raise EditorialContractError("representative first pass is not ready for human review")
    validate_first_pass_capture(gate.get("capture_review", {}))
    validate_tone_review(gate.get("tone_review", {}))
    if gate.get("rendered_page_reviewed") is not True:
        raise EditorialContractError("actual rendered/served pages were not reviewed")
    approval = gate.get("human_approval")
    if not isinstance(approval, dict) or approval.get("approved") is not True:
        raise EditorialContractError("explicit human first-pass approval is required")
    reviewer = str(approval.get("reviewed_by") or "").strip()
    if reviewer.lower() not in {"ray", "ray/assistant"}:
        raise EditorialContractError("first-pass approval must be recorded from Ray")
    if not str(approval.get("approved_at") or "").strip():
        raise EditorialContractError("human first-pass approval timestamp is required")


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
