import unittest
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace as NS
from unittest.mock import patch
from pathlib import Path

import venue_timezone as module


class VenueTimezoneTests(unittest.TestCase):
    def test_real_offline_ground_coordinates(self):
        for lat, lng, expected in [(40.8279, 14.1931, "Europe/Rome"), (44.36, 2.58, "Europe/Paris"), (40.823, -74.156, "America/New_York"), (-36.85, 174.76, "Pacific/Auckland")]:
            self.assertEqual(module.venue_timezone(NS(latitude=lat, longitude=lng)), expected)

    def test_invalid_missing_ocean_and_ambiguous_coordinates_fail_closed(self):
        for value in [None, NS(), NS(latitude=True, longitude=0), NS(latitude="40", longitude=14), NS(latitude=float("nan"), longitude=14), NS(latitude=100, longitude=14), NS(latitude=0, longitude=0)]:
            self.assertIsNone(module.venue_timezone(value))
        self.assertIsNone(module.venue_timezone(NS(latitude=43.8256, longitude=87.6168)))

    def test_cache_bounded_and_coordinates_keyed_not_team_or_venue_name(self):
        self.assertEqual(module._coordinate_timezone.cache_info().maxsize, 4096)
        venue = NS(latitude=40.8279, longitude=14.1931, name="Same name")
        self.assertEqual(module.venue_timezone(venue), "Europe/Rome")
        venue.latitude, venue.longitude = 40.823, -74.156
        self.assertEqual(module.venue_timezone(venue), "America/New_York")

    def test_uncertain_mismatched_invalid_and_failed_resolution_hide_action(self):
        for certain, zones in [(None, ["Europe/Rome"]), ("Europe/Rome", ["Europe/Rome", "Europe/Paris"]), ("Made/Up", ["Made/Up"])]:
            module._coordinate_timezone.cache_clear()
            with patch.object(module, "_finder") as finder:
                finder.certain_timezone_at.return_value = certain
                finder.timezones_at.return_value = zones
                self.assertIsNone(module.venue_timezone(NS(latitude=40, longitude=14)))
        module._coordinate_timezone.cache_clear()
        with patch.object(module, "_finder") as finder:
            finder.certain_timezone_at.side_effect = OSError("synthetic data failure")
            self.assertIsNone(module.venue_timezone(NS(latitude=40, longitude=14)))
        module._coordinate_timezone.cache_clear()

    def test_parallel_reads_safe(self):
        with ThreadPoolExecutor(max_workers=8) as pool:
            zones = list(pool.map(lambda n: module.venue_timezone(NS(latitude=40.8279 + n * .00001, longitude=14.1931)), range(32)))
        self.assertEqual(set(zones), {"Europe/Rome"})

    def test_existing_response_uses_canonical_ground_not_alias_or_home_club(self):
        import os
        if "@127.0.0.1:" not in os.environ.get("DATABASE_URL", ""):
            self.skipTest("Disposable local PostgreSQL required")
        from sqlalchemy.orm import Session
        from database import engine
        from models import Venue, Fixture
        from datetime import datetime, timezone
        import main
        with engine.connect() as connection:
            transaction = connection.begin()
            try:
                db = Session(bind=connection, join_transaction_mode="create_savepoint")
                canonical = Venue(venue_id=790001, name="Synthetic Napoli canonical", latitude=40.8279, longitude=14.1931)
                alias = Venue(venue_id=790002, name="Synthetic alias", canonical_venue_id=790001, equivalence_source="synthetic-test", latitude=40.823, longitude=-74.156)
                db.add(canonical); db.flush(); db.add(alias); db.flush()
                kickoff = datetime(2026, 10, 20, 18, tzinfo=timezone.utc)
                db.add(Fixture(fixture_id=1790000001, venue_id=790002, home_team="Synthetic", away_team="Other", fixture_date=kickoff, status="NS")); db.commit()
                with patch("main.SessionLocal", return_value=db):
                    response = main.get_fixture_social(1790000001, None)
                self.assertEqual(response["fixture"]["venue_timezone"], "Europe/Rome")
                self.assertEqual(response["fixture"]["fixture_date"], kickoff)
                self.assertEqual(response["fixture"]["venue_id"], 790001)
            finally:
                transaction.rollback()
