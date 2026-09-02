import unittest
from datetime import date, datetime, timezone
from types import SimpleNamespace

from decision import (
    DECISION_ATTRIBUTES,
    applicable_decision_payload,
    canonical_team_pair,
    fixture_decision_payload,
    fixture_decision_leads,
    validate_decision_fact,
)
from models import DecisionFact


def fact(
    fact_id,
    attribute_key,
    *,
    subject_type=None,
    status="PUBLISHED",
    effective_from=None,
    effective_to=None,
    label=None,
    team_a_id=None,
    team_b_id=None,
    venue_id=None,
):
    definition = DECISION_ATTRIBUTES[attribute_key]
    return SimpleNamespace(
        fact_id=fact_id,
        subject_type=subject_type or definition.allowed_subject,
        attribute_key=attribute_key,
        label=label or attribute_key.replace("_", " ").title(),
        explanation=f"Evidence-backed explanation for {attribute_key}.",
        publication_status=status,
        effective_from=effective_from,
        effective_to=effective_to,
        team_a_id=team_a_id,
        team_b_id=team_b_id,
        venue_id=venue_id,
    )


class FakeQuery:
    def __init__(self, rows):
        self.rows = rows

    def filter(self, *conditions):
        return self

    def all(self):
        return self.rows


class FakeSession:
    def __init__(self, rows):
        self.rows = rows
        self.query_calls = 0

    def query(self, model):
        self.model = model
        self.query_calls += 1
        return FakeQuery(self.rows)


class DecisionV1Tests(unittest.TestCase):
    def test_team_pair_is_order_independent(self):
        self.assertEqual(canonical_team_pair(20, 10), (10, 20))
        model = DecisionFact(
            subject_type="TEAM_PAIR", team_a_id=20, team_b_id=10,
            attribute_key="SIGNIFICANT_RIVALRY", label="A rivalry", explanation="A reviewed rivalry.",
        )
        self.assertEqual((model.team_a_id, model.team_b_id), (10, 20))

    def test_invalid_attribute_subject_combination_is_rejected(self):
        with self.assertRaises(ValueError):
            validate_decision_fact("VENUE", "SIGNIFICANT_RIVALRY")
        with self.assertRaises(ValueError):
            DecisionFact(
                subject_type="TEAM_PAIR", team_a_id=1, team_b_id=2,
                attribute_key="CLASSIC_GROUND", label="Wrong", explanation="Wrong subject.",
            )

    def test_unpublished_and_out_of_period_facts_fail_closed(self):
        rows = [
            fact(1, "SIGNIFICANT_RIVALRY", status="DRAFT"),
            fact(2, "FOOTBALL_LANDMARK", status="REJECTED"),
            fact(3, "UNIQUE_SETTING", effective_to=date(2026, 7, 31)),
            fact(4, "CLASSIC_GROUND", effective_from=date(2026, 9, 2)),
        ]
        payload = applicable_decision_payload(rows, date(2026, 9, 1))
        self.assertEqual(payload, {"decision_reasons": [], "highlight_eligible": False})

    def test_published_team_pair_and_venue_reasons_are_deterministic(self):
        rows = [
            fact(4, "CLASSIC_GROUND", label="Classic ground"),
            fact(1, "SIGNIFICANT_RIVALRY", label="East Lancashire Derby"),
            fact(2, "FOOTBALL_LANDMARK", label="Football landmark"),
        ]
        payload = applicable_decision_payload(rows, datetime(2026, 9, 1, tzinfo=timezone.utc))
        self.assertEqual([row["key"] for row in payload["decision_reasons"]], [
            "SIGNIFICANT_RIVALRY", "FOOTBALL_LANDMARK", "CLASSIC_GROUND",
        ])
        self.assertEqual([row["emoji"] for row in payload["decision_reasons"]], ["🔥", "🏟️", "🧱"])
        self.assertTrue(payload["highlight_eligible"])

    def test_fixture_inherits_a_published_venue_fact(self):
        fixture = SimpleNamespace(
            home_team_id=None, away_team_id=None, venue_id=99,
            fixture_date=datetime(2026, 9, 1, tzinfo=timezone.utc),
        )
        payload = fixture_decision_payload(FakeSession([fact(3, "UNIQUE_SETTING")]), fixture)
        self.assertEqual(payload["decision_reasons"][0]["key"], "UNIQUE_SETTING")
        self.assertTrue(payload["highlight_eligible"])

    def test_no_subject_or_no_applicable_fact_is_not_highlighted(self):
        fixture = SimpleNamespace(
            home_team_id=None, away_team_id=None, venue_id=None,
            fixture_date=datetime(2026, 9, 1, tzinfo=timezone.utc),
        )
        self.assertEqual(
            fixture_decision_payload(FakeSession([]), fixture),
            {"decision_reasons": [], "highlight_eligible": False},
        )
        self.assertEqual(
            applicable_decision_payload([fact(1, "SIGNIFICANT_RIVALRY")], None),
            {"decision_reasons": [], "highlight_eligible": False},
        )

    def test_emoji_is_controlled_and_duplicate_facts_are_suppressed(self):
        with self.assertRaises(TypeError):
            DecisionFact(
                subject_type="VENUE", venue_id=1, attribute_key="CLASSIC_GROUND",
                label="Classic", explanation="A classic ground.", emoji="❌",
            )
        duplicate = fact(8, "CLASSIC_GROUND", label="Classic ground")
        payload = applicable_decision_payload([duplicate, fact(9, "CLASSIC_GROUND", label="Classic ground")], date(2026, 9, 1))
        self.assertEqual(len(payload["decision_reasons"]), 1)

    def test_database_indexes_prevent_duplicate_subject_attributes(self):
        unique_indexes = {index.name for index in DecisionFact.__table__.indexes if index.unique}
        self.assertEqual(unique_indexes, {
            "uq_decision_facts_team_pair_attribute",
            "uq_decision_facts_venue_attribute",
        })

    def test_bulk_discover_resolution_returns_false_null_for_ordinary_fixture(self):
        fixture = SimpleNamespace(
            fixture_id=10, home_team_id=1, away_team_id=2, venue_id=3,
            fixture_date=datetime(2026, 9, 1, tzinfo=timezone.utc),
        )
        session = FakeSession([])
        self.assertEqual(fixture_decision_leads(session, [fixture]), {
            10: {"highlight_eligible": False, "lead_decision_reason": None},
        })
        self.assertEqual(session.query_calls, 1)

    def test_bulk_discover_resolution_uses_one_query_and_rivalry_precedence(self):
        fixtures = [
            SimpleNamespace(fixture_id=10, home_team_id=40, away_team_id=33, venue_id=23100, fixture_date=datetime(2026, 9, 1, tzinfo=timezone.utc)),
            SimpleNamespace(fixture_id=11, home_team_id=8, away_team_id=9, venue_id=23100, fixture_date=datetime(2026, 9, 2, tzinfo=timezone.utc)),
        ]
        session = FakeSession([
            fact(2, "FOOTBALL_LANDMARK", venue_id=23100, label="Football landmark"),
            fact(1, "SIGNIFICANT_RIVALRY", team_a_id=33, team_b_id=40, label="Historic rivalry"),
        ])
        payloads = fixture_decision_leads(session, fixtures)
        self.assertEqual(session.query_calls, 1)
        self.assertTrue(payloads[10]["highlight_eligible"])
        self.assertTrue(payloads[11]["highlight_eligible"])
        self.assertEqual(payloads[10]["lead_decision_reason"]["key"], "SIGNIFICANT_RIVALRY")
        self.assertEqual(payloads[11]["lead_decision_reason"]["key"], "FOOTBALL_LANDMARK")

    def test_bulk_discover_tie_is_deterministic_by_normalized_label_then_fact_id(self):
        fixture = SimpleNamespace(
            fixture_id=10, home_team_id=1, away_team_id=2, venue_id=99,
            fixture_date=datetime(2026, 9, 1, tzinfo=timezone.utc),
        )
        session = FakeSession([
            fact(5, "CLASSIC_GROUND", venue_id=99, label="Ａlpha"),
            fact(7, "CLASSIC_GROUND", venue_id=99, label="Alpha"),
        ])
        payload = fixture_decision_leads(session, [fixture])[10]
        self.assertEqual(payload["lead_decision_reason"]["label"], "Ａlpha")


if __name__ == "__main__":
    unittest.main()
