"""Classify researched KNOW proposals and emit only useful human-review rows."""

AUTO_APPROVED = "AUTO_APPROVED"
HUMAN_REVIEW = "HUMAN_REVIEW"
NO_EVIDENCE = "NO_EVIDENCE"
SPOT_TYPES = {"SUPPORTER_SPOT", "CLUB_MATCHDAY_VENUE", "SUPPORTER_AREA"}


def classify(proposal):
    if not proposal.get("candidate") or not proposal.get("supporter_wording") or not proposal.get("best_evidence"):
        return NO_EVIDENCE
    if proposal.get("classification") not in SPOT_TYPES and proposal.get("content_type") == "pre_match_spot":
        return HUMAN_REVIEW
    strong = proposal.get("evidence_strength") == "STRONG"
    publishable = proposal.get("publication_eligible") is True
    if strong and publishable:
        return AUTO_APPROVED
    return HUMAN_REVIEW


def build_review_queue(proposals):
    queue = []
    classifications = {AUTO_APPROVED: [], HUMAN_REVIEW: [], NO_EVIDENCE: []}
    for proposal in proposals:
        state = classify(proposal)
        classifications[state].append(proposal)
        if state == HUMAN_REVIEW:
            queue.append({
                "club": proposal["club"],
                "candidate": proposal["candidate"],
                "proposed_classification": proposal.get("classification"),
                "proposed_supporter_wording": proposal["supporter_wording"],
                "why_not_auto_approved": proposal.get("review_reason", "Evidence needs a human decision."),
                "best_supporting_evidence": proposal["best_evidence"],
                "decision": "APPROVE / REJECT / AMEND",
            })
    return classifications, queue
