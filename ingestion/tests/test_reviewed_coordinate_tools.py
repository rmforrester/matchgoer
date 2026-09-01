import json
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

from sqlalchemy import Column, Float, Integer, MetaData, String, Table, create_engine, select

from audit_ambiguous_coordinates import build_report
from ingestion.apply_reviewed_coordinates import (
    accepted_from_checkpoint,
    accepted_from_review_report,
    apply_coordinate_plan,
    build_plan,
    enforce_expected_updates,
    resolve_provider_venue_ids,
    reconcile,
    verify_expected_coordinate_rows,
    verify_withheld_coordinate_rows,
    baseline_coordinate,
    baseline_coordinate_matches,
    capture_baseline,
)


class ReviewedCoordinateToolTests(unittest.TestCase):
    def test_decimal_baseline_coordinates_round_trip_through_json(self):
        payload = {
            "target_rows": {
                "19785": {
                    "latitude": baseline_coordinate(Decimal("38.0371870")),
                    "longitude": baseline_coordinate(Decimal("23.7409320")),
                }
            }
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "baseline.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            loaded = json.loads(path.read_text(encoding="utf-8"))["target_rows"]["19785"]
        self.assertEqual(loaded, {"latitude": "38.037187", "longitude": "23.740932"})
        self.assertTrue(baseline_coordinate_matches(Decimal("38.037187"), loaded["latitude"]))
        self.assertTrue(baseline_coordinate_matches(Decimal("23.740932"), loaded["longitude"]))

    def test_checkpoint_retains_reviewed_withheld_ids_for_reconciliation(self):
        accepted, withheld = accepted_from_checkpoint({
            "3512": {"status": "withheld", "latitude": 1, "longitude": 2},
            "999": {"status": "geocoded", "latitude": 1, "longitude": 2},
        })
        self.assertEqual([item["provider_venue_id"] for item in accepted], [999])
        self.assertEqual(withheld, [3512])

    def test_prior_operation_ready_venue_does_not_block_later_baseline(self):
        engine, venues = self.baseline_table()
        with engine.begin() as connection:
            connection.execute(venues.insert(), [
                {"venue_id": 1, "provider_venue_id": 775, "name": "Karaiskakis", "city": "Piraeus", "country": "Greece", "latitude": 37.946, "longitude": 23.664},
                {"venue_id": 2, "provider_venue_id": 1504, "name": "Swedish ground", "city": "City", "country": "Sweden", "latitude": None, "longitude": None},
            ])
        planned = [{"venue_id": 2, "provider_venue_id": 1504, "latitude": 59.1, "longitude": 18.1}]
        with tempfile.TemporaryDirectory() as directory, engine.connect() as connection:
            baseline = capture_baseline(connection, venues, planned, [], Path(directory) / "baseline.json")
        self.assertEqual(set(baseline["target_rows"]), {"1504"})

    def test_sequential_baselines_are_operation_scoped_and_withheld_is_captured(self):
        engine, venues = self.baseline_table()
        with engine.begin() as connection:
            connection.execute(venues.insert(), [
                {"venue_id": 1, "provider_venue_id": 10, "name": "First", "city": "A", "country": "X"},
                {"venue_id": 2, "provider_venue_id": 20, "name": "Second", "city": "B", "country": "Y"},
                {"venue_id": 3, "provider_venue_id": 30, "name": "Withheld", "city": "C", "country": "Y"},
            ])
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with engine.connect() as connection:
                first = capture_baseline(connection, venues, [{"provider_venue_id": 10}], [], root / "first.json")
            with engine.begin() as connection:
                connection.execute(venues.update().where(venues.c.provider_venue_id == 10).values(latitude=1, longitude=2))
            with engine.connect() as connection:
                second = capture_baseline(connection, venues, [{"provider_venue_id": 20}], [30], root / "second.json")
        self.assertEqual(set(first["target_rows"]), {"10"})
        self.assertEqual(set(second["target_rows"]), {"20", "30"})
        self.assertNotIn("10", second["target_rows"])

    def test_current_operation_withheld_coordinates_must_remain_unchanged(self):
        baseline = {"30": {"latitude": None, "longitude": None}}
        verify_withheld_coordinate_rows(
            [30], {30: [SimpleNamespace(latitude=None, longitude=None)]}, baseline,
        )
        with self.assertRaisesRegex(RuntimeError, "Withheld provider venues changed"):
            verify_withheld_coordinate_rows(
                [30], {30: [SimpleNamespace(latitude=1.0, longitude=2.0)]}, baseline,
            )

    def test_core_reconciliation_does_not_require_cohort_metrics(self):
        engine, venues = self.baseline_table()
        with engine.begin() as connection:
            connection.execute(venues.insert(), {
                "venue_id": 1, "provider_venue_id": 1504, "name": "Swedish ground",
                "city": "City", "country": "Sweden", "latitude": 59.1, "longitude": 18.1,
            })
        accepted = [{
            "venue_id": 1, "provider_venue_id": 1504,
            "latitude": 59.1, "longitude": 18.1,
        }]
        baseline = {
            "planned_provider_venue_ids": [1504],
            "target_rows": {"1504": {
                "venue_id": 1, "name": "Swedish ground", "city": "City",
                "country": "Sweden", "latitude": None, "longitude": None,
            }},
            "venue_row_count": 1,
        }
        with engine.connect() as connection:
            report = reconcile(connection, venues, None, accepted, [], baseline)
        self.assertEqual(report["status"], "PASS")
        self.assertEqual(report["intended_coordinates_verified"], 1)
        self.assertNotIn("cohort_fixture_coverage", report)

    def baseline_table(self):
        engine = create_engine("sqlite://")
        metadata = MetaData()
        venues = Table(
            "venues", metadata,
            Column("venue_id", Integer, primary_key=True),
            Column("provider_venue_id", Integer, unique=True),
            Column("name", String), Column("city", String), Column("country", String),
            Column("latitude", Float), Column("longitude", Float),
        )
        metadata.create_all(engine)
        return engine, venues

    def test_provider_id_must_resolve_once(self):
        engine = create_engine("sqlite://")
        metadata = MetaData()
        venues = Table(
            "venues", metadata,
            Column("venue_id", Integer, primary_key=True),
            Column("provider_venue_id", Integer),
        )
        metadata.create_all(engine)
        with engine.begin() as connection:
            connection.execute(venues.insert(), [
                {"venue_id": 1, "provider_venue_id": 10},
                {"venue_id": 2, "provider_venue_id": 20},
                {"venue_id": 3, "provider_venue_id": 20},
            ])
        with engine.connect() as connection:
            accepted = [{"provider_venue_id": 10, "venue_id": None}]
            resolve_provider_venue_ids(connection, venues, accepted)
            self.assertEqual(accepted[0]["venue_id"], 1)
            with self.assertRaisesRegex(RuntimeError, "resolve uniquely"):
                resolve_provider_venue_ids(connection, venues, [{"provider_venue_id": 99, "venue_id": None}])
            with self.assertRaisesRegex(RuntimeError, "resolve uniquely"):
                resolve_provider_venue_ids(connection, venues, [{"provider_venue_id": 20, "venue_id": None}])

    def test_existing_coordinates_are_preserved_and_null_rows_are_planned(self):
        accepted = [
            {"venue_id": 1, "latitude": 1.0, "longitude": 2.0},
            {"venue_id": 2, "latitude": 3.0, "longitude": 4.0},
        ]
        rows = {
            1: SimpleNamespace(latitude=50.0, longitude=-1.0),
            2: SimpleNamespace(latitude=None, longitude=None),
        }
        planned, preserved = build_plan(accepted, rows)
        self.assertEqual([item["venue_id"] for item in planned], [2])
        self.assertEqual([item["venue_id"] for item in preserved], [1])

    def coordinate_table(self, count=100):
        engine = create_engine("sqlite://")
        metadata = MetaData()
        venues = Table(
            "venues", metadata,
            Column("venue_id", Integer, primary_key=True),
            Column("provider_venue_id", Integer),
            Column("latitude", Float), Column("longitude", Float),
        )
        metadata.create_all(engine)
        with engine.begin() as connection:
            connection.execute(venues.insert(), [
                {"venue_id": index, "provider_venue_id": 1000 + index}
                for index in range(1, count + 1)
            ])
        return engine, venues

    def test_expected_99_actual_99_is_allowed(self):
        engine, venues = self.coordinate_table(99)
        plan = [
            {"venue_id": index, "latitude": 10.0, "longitude": 20.0}
            for index in range(1, 100)
        ]
        self.assertEqual(apply_coordinate_plan(engine, venues, plan, 99), 99)
        with engine.connect() as connection:
            self.assertEqual(connection.execute(
                select(venues.c.venue_id).where(venues.c.latitude.is_not(None))
            ).all(), [(index,) for index in range(1, 100)])

    def test_expected_count_mismatch_aborts_before_any_write(self):
        for actual in (98, 100):
            engine, venues = self.coordinate_table(actual)
            plan = [
                {"venue_id": index, "latitude": 10.0, "longitude": 20.0}
                for index in range(1, actual + 1)
            ]
            with self.assertRaisesRegex(RuntimeError, "refusing write"):
                apply_coordinate_plan(engine, venues, plan, 99)
            with engine.connect() as connection:
                self.assertEqual(connection.execute(
                    select(venues.c.venue_id).where(venues.c.latitude.is_not(None))
                ).all(), [])

    def test_existing_valid_coordinate_is_never_targeted_or_overwritten(self):
        engine, venues = self.coordinate_table(2)
        with engine.begin() as connection:
            connection.execute(venues.update().where(venues.c.venue_id == 1).values(latitude=1.0, longitude=2.0))
        with engine.connect() as connection:
            rows = {row.venue_id: row for row in connection.execute(select(venues))}
        accepted = [
            {"venue_id": 1, "latitude": 8.0, "longitude": 9.0},
            {"venue_id": 2, "latitude": 3.0, "longitude": 4.0},
        ]
        planned, _ = build_plan(accepted, rows)
        apply_coordinate_plan(engine, venues, planned, 1)
        with engine.connect() as connection:
            row = connection.execute(select(venues).where(venues.c.venue_id == 1)).one()
            self.assertEqual((row.latitude, row.longitude), (1.0, 2.0))

    def test_reconciliation_accepts_correct_and_rejects_wrong_coordinates(self):
        accepted = [{"provider_venue_id": 10, "latitude": 1.5, "longitude": 2.5}]
        verify_expected_coordinate_rows(accepted, {10: [SimpleNamespace(latitude=1.5, longitude=2.5)]})
        with self.assertRaisesRegex(RuntimeError, "Missing or unexpected"):
            verify_expected_coordinate_rows(accepted, {10: [SimpleNamespace(latitude=1.6, longitude=2.5)]})
        with self.assertRaisesRegex(RuntimeError, "resolve uniquely"):
            verify_expected_coordinate_rows(accepted, {})

    def test_reconciliation_compares_at_hosted_numeric_six_decimal_scale(self):
        accepted = [{
            "provider_venue_id": 19929,
            "latitude": 37.9871895,
            "longitude": 23.7541388,
        }]
        verify_expected_coordinate_rows(accepted, {
            19929: [SimpleNamespace(
                latitude=Decimal("37.987190"),
                longitude=Decimal("23.754139"),
            )]
        })
        with self.assertRaisesRegex(RuntimeError, "Missing or unexpected"):
            verify_expected_coordinate_rows(accepted, {
                19929: [SimpleNamespace(
                    latitude=Decimal("37.987192"),
                    longitude=Decimal("23.754139"),
                )]
            })

    def test_legacy_review_report_shape_still_works(self):
        payload = {"venues": [{
            "status": "accepted", "latitude": 1, "longitude": 2,
            "venue": {"venue_id": 7, "provider_venue_id": 70},
        }, {"status": "wrong_city", "venue": {"venue_id": 8}}]}
        self.assertEqual(accepted_from_review_report(payload)[0]["venue_id"], 7)

    def test_selected_provider_ids_bound_the_review_report(self):
        checkpoint = {
            "10": {"status": "ambiguous"},
            "20": {"status": "ambiguous"},
        }
        catalog = {
            "10": {"provider_venue_id": 10, "name": "One", "city": "City", "country": "Country"},
            "20": {"provider_venue_id": 20, "name": "Two", "city": "City", "country": "Country"},
        }
        cache = {"10": {"error": None, "candidates": []}, "20": {"error": None, "candidates": []}}
        report = build_report(checkpoint, catalog, cache, {"20"})
        self.assertEqual([item["venue_id"] for item in report["venues"]], [20])


if __name__ == "__main__":
    unittest.main()
