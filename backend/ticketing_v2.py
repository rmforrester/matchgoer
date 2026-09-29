"""Ticketing V2 T1 state vocabulary and fail-closed current-state rules."""
from datetime import datetime
from urllib.parse import urlparse

SOURCE_STATES = frozenset({
    "VERIFIED_DIRECT_PURCHASE_SOURCE", "VERIFIED_OFFICIAL_TICKET_NAVIGATION_SOURCE",
    "PAY_AT_GATE_OR_OFFLINE_SOURCE", "FIXTURE_SPECIFIC_TICKETING", "NO_ONLINE_SALES",
    "NO_SAFE_TICKET_SOURCE", "SOURCE_NEEDS_REVIEW", "SOURCE_STALE",
})
AVAILABILITY_STATES = frozenset({
    "ON_SALE", "NOT_ON_SALE_YET", "SALE_STATUS_UNKNOWN", "SOLD_OUT", "PAY_AT_GATE",
    "OFFLINE_PURCHASE", "FIXTURE_SPECIFIC_GUIDANCE", "NO_SAFE_TICKET_INFORMATION",
    "MATCHING_REVIEW_REQUIRED", "CANCELLED_OR_NOT_APPLICABLE",
})
MATCHING_OUTCOMES = frozenset({
    "MATCHED_CANONICAL_FIXTURE", "NO_CANONICAL_MATCH", "MULTIPLE_POSSIBLE_MATCHES",
    "DATE_OR_OPPONENT_CONFLICT", "FIXTURE_NOT_IN_MATCHGOER", "MATCHING_REVIEW_REQUIRED",
})

RESEARCH_RESOLUTION_STATES = frozenset({
    "RESOLVED_ONLINE", "RESOLVED_PHYSICAL", "NO_SAFE_ROUTE_FOUND",
})
ONLINE_ROUTE_TYPES = frozenset({
    "ONLINE_OFFICIAL_SHOP", "ONLINE_AUTHORIZED_PROVIDER",
    "ONLINE_OFFICIAL_HUB", "ONLINE_OFFICIAL_APP",
})
PHYSICAL_ROUTE_TYPES = frozenset({
    "PHYSICAL_CLUB_OFFICE", "PHYSICAL_PRE_SALE_POINT",
    "PHYSICAL_MATCHDAY_BOX_OFFICE", "DIRECT_CLUB_ORDER",
})
TICKET_DESTINATION_TERMS = ("ticket", "karten", "billet", "bigliett", "bilet", "eisit")

def validate_state(value, allowed, label):
    if value not in allowed:
        raise ValueError(f"unsupported {label}: {value}")
    return value


def validate_research_result(row):
    """Validate CTA completeness before a ticket-research row is consolidated.

    This is intentionally narrower than source publication validation. Research
    may safely conclude that no route exists, but it may not call an online
    result resolved without a machine-usable CTA.
    """
    required = ("canonical_team_id", "route_type", "source_url", "source_date", "evidence", "resolution_state")
    missing = [field for field in required if not str(row.get(field) or "").strip()]
    if missing:
        raise ValueError("missing ticket research fields: " + ", ".join(missing))
    state = validate_state(row["resolution_state"], RESEARCH_RESOLUTION_STATES, "research resolution state")
    route_type = row["route_type"]
    if state == "RESOLVED_ONLINE":
        if route_type not in ONLINE_ROUTE_TYPES:
            raise ValueError("resolved online row requires an approved online route type")
        actionable = str(row.get("actionable_url") or "").strip()
        parsed = urlparse(actionable)
        if parsed.scheme != "https" or not parsed.netloc:
            raise ValueError("resolved online row requires an actionable HTTPS CTA")
    elif state == "RESOLVED_PHYSICAL":
        if route_type not in PHYSICAL_ROUTE_TYPES:
            raise ValueError("resolved physical row requires an approved physical/direct route type")
        if not str(row.get("instructions") or "").strip():
            raise ValueError("resolved physical row requires structured instructions")
        if route_type == "PHYSICAL_MATCHDAY_BOX_OFFICE" and not str(row.get("venue_applicability") or "").strip():
            raise ValueError("matchday box-office research requires venue applicability")
    elif state == "NO_SAFE_ROUTE_FOUND" and row.get("actionable_url"):
        raise ValueError("no-safe-route result cannot carry an actionable CTA")
    return row


def validate_publication_destination(row, probe):
    """Fail closed on the live destination evidence used by publication QA.

    Network probing remains outside this pure validator. The caller supplies a
    captured probe so tests and protected writes stay deterministic.
    """
    url = str(row.get("source_url") or "").strip()
    if not url:
        if row.get("actionable_official_url"):
            raise ValueError("physical guidance cannot supersede an actionable official ticket page")
        label = str(row.get("source_label") or "").lower()
        if any(term in label for term in ("online", "ticketshop", "ticket-shop")):
            raise ValueError("offline source label contradicts its missing actionable URL")
        return row
    if not probe:
        raise ValueError("online publication requires captured live destination evidence")
    if not probe.get("tls_valid"):
        raise ValueError("ticket destination TLS validation failed")
    status = int(probe.get("status") or 0)
    if status < 200 or status >= 400:
        raise ValueError("ticket destination did not return a usable HTTP status")
    final_url = str(probe.get("final_url") or "")
    parsed = urlparse(final_url)
    if parsed.scheme != "https" or not parsed.netloc:
        raise ValueError("ticket destination did not resolve to HTTPS")
    if probe.get("irrelevant_redirect"):
        raise ValueError("ticket destination redirected outside the approved ticket route")
    if not probe.get("actionable_ticket_destination"):
        raise ValueError("ticket destination is generic or non-actionable")
    return row

def derive_current_state(observations, now: datetime):
    """Return one safe current observation, or an explicit unknown/review result."""
    valid = [o for o in observations
             if o["matching_outcome"] == "MATCHED_CANONICAL_FIXTURE"
             and (o.get("valid_until") is None or o["valid_until"] >= now)]
    if not valid:
        return {"availability_state": "SALE_STATUS_UNKNOWN", "observation": None}
    newest_at = max(o["observed_at"] for o in valid)
    newest = [o for o in valid if o["observed_at"] == newest_at]
    states = {o["observed_state"] for o in newest}
    if len(states) != 1:
        return {"availability_state": "MATCHING_REVIEW_REQUIRED", "observation": None}
    return {"availability_state": newest[0]["observed_state"], "observation": newest[0]}
