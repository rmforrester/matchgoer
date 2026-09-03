from dataclasses import dataclass
from datetime import date, datetime
import unicodedata

from sqlalchemy import and_, or_, tuple_


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
    "EXCEPTIONAL_SUPPORT": DecisionAttributeDefinition("PRIMARY", "📣", "TEAM", 5),
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


def _normalized_label(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value).casefold().split())


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
            "_lead": 0 if getattr(fact, "lead_priority", "NORMAL") == "LEAD" else 1,
            "_order": definition.order,
            "_fact_id": fact.fact_id or 0,
        })
    reasons.sort(key=lambda row: (row["_lead"], row["_order"], _normalized_label(row["label"]), row["_fact_id"]))
    for reason in reasons:
        reason.pop("_lead")
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
    if fixture.home_team_id is not None:
        subjects.append(and_(DecisionFact.subject_type == "TEAM", DecisionFact.team_id == fixture.home_team_id))
    if not subjects:
        return {"decision_reasons": [], "highlight_eligible": False}

    facts = (
        db.query(DecisionFact)
        .filter(DecisionFact.publication_status == "PUBLISHED", or_(*subjects))
        .all()
    )
    return applicable_decision_payload(facts, fixture.fixture_date)


def fixture_decision_leads(db, fixtures) -> dict[int, dict]:
    """Resolve Discover's lead reason for a fixture cohort with one fact query."""
    from models import DecisionFact

    fixture_rows = list(fixtures)
    if not fixture_rows:
        return {}
    pairs = {
        canonical_team_pair(item.home_team_id, item.away_team_id)
        for item in fixture_rows
        if item.home_team_id is not None
        and item.away_team_id is not None
        and item.home_team_id != item.away_team_id
    }
    venue_ids = {item.venue_id for item in fixture_rows if item.venue_id is not None}
    home_team_ids = {item.home_team_id for item in fixture_rows if item.home_team_id is not None}
    subject_filters = []
    if pairs:
        subject_filters.append(and_(
            DecisionFact.subject_type == "TEAM_PAIR",
            tuple_(DecisionFact.team_a_id, DecisionFact.team_b_id).in_(sorted(pairs)),
        ))
    if venue_ids:
        subject_filters.append(and_(
            DecisionFact.subject_type == "VENUE",
            DecisionFact.venue_id.in_(sorted(venue_ids)),
        ))
    if home_team_ids:
        subject_filters.append(and_(
            DecisionFact.subject_type == "TEAM",
            DecisionFact.team_id.in_(sorted(home_team_ids)),
        ))
    if not subject_filters:
        return {
            item.fixture_id: {"highlight_eligible": False, "lead_decision_reason": None}
            for item in fixture_rows
        }

    facts = (
        db.query(DecisionFact)
        .filter(DecisionFact.publication_status == "PUBLISHED", or_(*subject_filters))
        .all()
    )
    pair_facts = {}
    venue_facts = {}
    team_facts = {}
    for fact in facts:
        if fact.subject_type == "TEAM_PAIR":
            pair_facts.setdefault((fact.team_a_id, fact.team_b_id), []).append(fact)
        elif fact.subject_type == "VENUE":
            venue_facts.setdefault(fact.venue_id, []).append(fact)
        elif fact.subject_type == "TEAM":
            team_facts.setdefault(fact.team_id, []).append(fact)

    resolved = {}
    for item in fixture_rows:
        applicable = list(venue_facts.get(item.venue_id, []))
        applicable.extend(team_facts.get(item.home_team_id, []))
        if item.home_team_id is not None and item.away_team_id is not None and item.home_team_id != item.away_team_id:
            applicable.extend(pair_facts.get(canonical_team_pair(item.home_team_id, item.away_team_id), []))
        payload = applicable_decision_payload(applicable, item.fixture_date)
        resolved[item.fixture_id] = {
            "highlight_eligible": payload["highlight_eligible"],
            "lead_decision_reason": payload["decision_reasons"][0] if payload["decision_reasons"] else None,
        }
    return resolved
