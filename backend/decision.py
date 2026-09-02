from dataclasses import dataclass
from datetime import date, datetime

from sqlalchemy import and_, or_


@dataclass(frozen=True)
class DecisionAttributeDefinition:
    importance: str
    emoji: str
    allowed_subject: str
    order: int


DECISION_ATTRIBUTES = {
    "SIGNIFICANT_RIVALRY": DecisionAttributeDefinition("PRIMARY", "🔥", "TEAM_PAIR", 1),
    "FOOTBALL_LANDMARK": DecisionAttributeDefinition("PRIMARY", "🏟️", "VENUE", 2),
    "UNIQUE_SETTING": DecisionAttributeDefinition("PRIMARY", "🏞️", "VENUE", 3),
    "CLASSIC_GROUND": DecisionAttributeDefinition("PRIMARY", "🧱", "VENUE", 4),
}


def validate_decision_fact(subject_type: str, attribute_key: str) -> DecisionAttributeDefinition:
    definition = DECISION_ATTRIBUTES.get(attribute_key)
    if definition is None or definition.allowed_subject != subject_type:
        raise ValueError(f"Unsupported DECIDE attribute/subject combination: {attribute_key}/{subject_type}")
    return definition


def canonical_team_pair(team_a_id: int, team_b_id: int) -> tuple[int, int]:
    if team_a_id == team_b_id:
        raise ValueError("A DECIDE team pair requires two distinct teams")
    return tuple(sorted((team_a_id, team_b_id)))


def _fixture_day(value: date | datetime) -> date:
    return value.date() if isinstance(value, datetime) else value


def applicable_decision_payload(facts, fixture_date: date | datetime | None) -> dict:
    if fixture_date is None:
        return {"decision_reasons": [], "highlight_eligible": False}
    day = _fixture_day(fixture_date)
    reasons = []
    seen = set()
    for fact in facts:
        if fact.publication_status != "PUBLISHED":
            continue
        if fact.effective_from and day < fact.effective_from:
            continue
        if fact.effective_to and day > fact.effective_to:
            continue
        try:
            definition = validate_decision_fact(fact.subject_type, fact.attribute_key)
        except ValueError:
            continue
        identity = (fact.attribute_key, fact.label, fact.explanation)
        if identity in seen:
            continue
        seen.add(identity)
        reasons.append({
            "key": fact.attribute_key,
            "emoji": definition.emoji,
            "label": fact.label,
            "explanation": fact.explanation,
            "importance": definition.importance,
            "_order": definition.order,
            "_fact_id": fact.fact_id or 0,
        })
    reasons.sort(key=lambda row: (row["_order"], row["label"].casefold(), row["_fact_id"]))
    for reason in reasons:
        reason.pop("_order")
        reason.pop("_fact_id")
    return {
        "decision_reasons": reasons,
        "highlight_eligible": any(reason["importance"] == "PRIMARY" for reason in reasons),
    }


def fixture_decision_payload(db, fixture) -> dict:
    from models import DecisionFact

    subjects = []
    if fixture.home_team_id is not None and fixture.away_team_id is not None and fixture.home_team_id != fixture.away_team_id:
        team_a_id, team_b_id = canonical_team_pair(fixture.home_team_id, fixture.away_team_id)
        subjects.append(and_(
            DecisionFact.subject_type == "TEAM_PAIR",
            DecisionFact.team_a_id == team_a_id,
            DecisionFact.team_b_id == team_b_id,
        ))
    if fixture.venue_id is not None:
        subjects.append(and_(DecisionFact.subject_type == "VENUE", DecisionFact.venue_id == fixture.venue_id))
    if not subjects:
        return {"decision_reasons": [], "highlight_eligible": False}

    facts = (
        db.query(DecisionFact)
        .filter(DecisionFact.publication_status == "PUBLISHED", or_(*subjects))
        .all()
    )
    return applicable_decision_payload(facts, fixture.fixture_date)
