"""Synthetic large-cohort regression; optional localhost-only PostgreSQL parity."""
from datetime import datetime, timedelta, timezone
import os
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, event, func, text
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from decision import fixture_decision_leads, fixture_decision_payload
from models import Base, DecisionFact, Fixture, Team, Venue


@pytest.fixture(params=["sqlite", "postgres"])
def database(request):
    if request.param == "postgres":
        url = os.getenv("DISCOVER_TEST_DATABASE_URL")
        if not url:
            pytest.skip("Set DISCOVER_TEST_DATABASE_URL for disposable PostgreSQL")
        from sqlalchemy.engine import make_url
        assert make_url(url).host == "127.0.0.1", "Disposable localhost database only"
        admin = create_engine(url)
        schema = "discover_test_" + uuid4().hex
        with admin.begin() as c:
            c.execute(text('CREATE SCHEMA "' + schema + '"'))
        engine = create_engine(url, connect_args={"options": "-c search_path=" + schema + " -c statement_timeout=15000"})
    else:
        engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
        @event.listens_for(engine, "connect")
        def functions(c, _):
            c.create_function("btrim", 1, lambda s: s.strip() if s else s)
            c.create_function("num_nonnulls", -1, lambda *v: sum(x is not None for x in v))
            c.create_function("char_length", 1, lambda s: len(s) if s is not None else None)
    Base.metadata.create_all(engine, tables=[t for t in Base.metadata.sorted_tables if t.name != "account_conversion_handoffs"])
    from backend.fixture_integrity import META
    META.create_all(engine)
    try:
        yield engine
    finally:
        engine.dispose()
        if request.param == "postgres":
            with admin.begin() as c:
                c.execute(text('DROP SCHEMA "' + schema + '" CASCADE'))
            admin.dispose()


def cohort(count):
    day = datetime.now(timezone.utc) + timedelta(days=2)
    return [SimpleNamespace(fixture_id=i+1, home_team_id=2*i+1, away_team_id=2*i+2,
                            venue_id=100, fixture_date=day) for i in range(count)]


def seed_editorial(db):
    db.add_all([Team(team_id=i, team_name="Synthetic " + str(i)) for i in [1, 2, 3, 4]])
    db.add(Venue(venue_id=100, name="Synthetic municipal ground", country="England", latitude=51, longitude=0))
    db.flush()
    facts = [
        dict(fact_id=1, subject_type="TEAM_PAIR", team_a_id=1, team_b_id=2, attribute_key="SIGNIFICANT_RIVALRY", label="Exact rivalry"),
        dict(fact_id=2, subject_type="TEAM_PAIR", team_a_id=1, team_b_id=4, attribute_key="SIGNIFICANT_RIVALRY", label="Not this pairing"),
        dict(fact_id=3, subject_type="VENUE", venue_id=100, attribute_key="CLASSIC_GROUND", label="Shared ground"),
        dict(fact_id=4, subject_type="TEAM", team_id=1, attribute_key="EXCEPTIONAL_SUPPORT", label="Home supporters"),
        dict(fact_id=5, subject_type="TEAM", team_id=2, attribute_key="EXCEPTIONAL_SUPPORT", label="Away must not leak"),
        dict(fact_id=6, subject_type="VENUE", venue_id=100, attribute_key="UNIQUE_SETTING", label="Draft must not leak", publication_status="DRAFT"),
        dict(fact_id=7, subject_type="VENUE", venue_id=100, attribute_key="FOOTBALL_LANDMARK", label="Expired must not leak", effective_to=datetime(2000, 1, 1).date()),
    ]
    for f in facts:
        f.setdefault("publication_status", "PUBLISHED")
        db.add(DecisionFact(**f, explanation=f["label"]))
    db.commit()


def test_large_inventory_one_exact_editorial_query(database):
    with Session(database) as db:
        seed_editorial(db)
        rows = cohort(20000)
        rows.append(rows[0])  # deduplicated cohort, not duplicate output
        # A reversed home/away pair must use the same rivalry, not away TEAM facts.
        rows.append(SimpleNamespace(fixture_id=30000, home_team_id=2, away_team_id=1,
                                    venue_id=None, fixture_date=rows[0].fixture_date))
        statements = []
        def capture(_c, _cur, sql, _params, _ctx, _many): statements.append(sql)
        event.listen(database, "before_cursor_execute", capture)
        try:
            result = fixture_decision_leads(db, rows)
        finally:
            event.remove(database, "before_cursor_execute", capture)
        assert len(statements) == 1
        assert "WITH discover_team_pairs" in statements[0]
        assert len(result) == 20001
        assert result[1]["lead_decision_reason"]["label"] == "Exact rivalry"
        labels = [x["label"] for x in result[1]["decision_reasons"]]
        assert labels == ["Exact rivalry", "Shared ground", "Home supporters"]
        assert result[2]["decision_attribute_keys"] == ["CLASSIC_GROUND"]
        assert result[30000]["decision_attribute_keys"] == ["SIGNIFICANT_RIVALRY", "EXCEPTIONAL_SUPPORT"]
        for row in [rows[0], rows[1], rows[-1]]:
            assert result[row.fixture_id]["decision_reasons"] == fixture_decision_payload(db, row)["decision_reasons"]


def test_empty_or_unknown_subjects_do_not_query(database):
    with Session(database) as db:
        assert fixture_decision_leads(db, []) == {}
        row = SimpleNamespace(fixture_id=1, home_team_id=None, away_team_id=None, venue_id=None,
                              fixture_date=datetime.now(timezone.utc))
        result = fixture_decision_leads(db, [row])[1]
        assert result == dict(highlight_eligible=False, lead_decision_reason=None,
                              decision_attribute_keys=[], decision_reasons=[])


def test_worldwide_api_counts_pages_filters_and_editorial(database, monkeypatch):
    import main
    from backend.tests.test_fixture_integrity_api import TestClient
    monkeypatch.setattr(main, "SessionLocal", sessionmaker(bind=database))
    if database.dialect.name == "sqlite":
        monkeypatch.setattr(main, "utc_date_expression", lambda col: func.date(col))
    # SQLite does not round-trip timezone information; match existing API tests.
    def aware(row, _):
        if row.fixture_date.tzinfo is None:
            row.fixture_date = row.fixture_date.replace(tzinfo=timezone.utc)
    event.listen(Fixture, "load", aware)
    try:
        with Session(database) as db:
            seed_editorial(db)
            db.execute(Team.__table__.insert(), [dict(team_id=i, team_name="Synthetic " + str(i)) for i in range(5, 24001)])
            db.add(Venue(venue_id=200, name="Synthetic shared complex", country="USA", latitude=40, longitude=-74))
            db.flush()
            rows = cohort(12000)
            db.execute(Fixture.__table__.insert(), [dict(fixture_id=r.fixture_id, fixture_date=r.fixture_date,
                home_team_id=r.home_team_id, away_team_id=r.away_team_id, home_team="Home", away_team="Away",
                venue_id=100 if r.fixture_id <= 6000 else 200, status="NS", league_id=1,
                league_name="Synthetic league", country="England" if r.fixture_id <= 6000 else "USA", season=2026) for r in rows])
            # Invalid/missing locations and inactive fixtures must not enter totals.
            for i, status, venue in [(50001, "PST", 100), (50002, "CANC", 100), (50003, "NS", None)]:
                db.add(Fixture(fixture_id=i, fixture_date=rows[0].fixture_date, home_team_id=1, away_team_id=2,
                    home_team="Home", away_team="Away", venue_id=venue, status=status, league_id=1, season=2026))
            db.commit()
        client = TestClient(main.app)
        params = dict(latitude=0, longitude=0, north=90, south=-90, west=-180, east=180, limit=20)
        first = client.get("/nearby", params=params)
        assert first.status_code == 200
        assert first.headers["X-Total-Matches"] == "12000"
        assert first.headers["X-Results-Limited"] == "true"
        assert [r["fixture_id"] for r in first.json()] == list(range(1, 21))
        assert first.json()[0]["lead_decision_reason"]["label"] == "Exact rivalry"
        second = client.get("/nearby", params={**params, "offset": 20})
        assert {r["fixture_id"] for r in first.json()}.isdisjoint(r["fixture_id"] for r in second.json())
        regional = client.get("/nearby", params={**params, "north": 52, "south": 50, "west": -1, "east": 1})
        assert regional.headers["X-Total-Matches"] == "6000"
        assert all(r["venue_id"] == 100 for r in regional.json())
        dated = client.get("/nearby", params={**params, "date": rows[0].fixture_date.date().isoformat(), "offset": 11990})
        assert dated.headers["X-Results-Limited"] == "false" and len(dated.json()) == 10
        none = client.get("/nearby", params={**params, "date": "2000-01-01"})
        assert none.json() == [] and none.headers["X-Total-Matches"] == "0"
    finally:
        event.remove(Fixture, "load", aware)
