"""Existing rating contracts: synthetic local records, no new production behaviour."""
from types import SimpleNamespace
from unittest.mock import patch
import unittest
from sqlalchemy.orm import Session
from fastapi import HTTPException
from backend.tests import test_terraces_b1 as fixtures
from models import AwayDayReview, VenueVisit
from schemas import AwayDayReviewUpdate
import main


class PersonalRatingTests(unittest.TestCase):
    def setUp(self):
        fixtures.PhotoB1Tests.setUp(self)
        self.sessions = patch('main.SessionLocal', lambda: Session(bind=self.connection, join_transaction_mode='create_savepoint'))
        self.sessions.start()
        self.db.add(AwayDayReview(user_id=self.owner.user_id, venue_id=self.venue.venue_id,
            atmosphere_score=8, pubs_score=7, getting_there_score=9, facilities_score=7,
            overall_score=7.8, recommend=True))
        self.db.commit()

    def tearDown(self):
        self.sessions.stop()
        fixtures.PhotoB1Tests.tearDown(self)

    def test_personal_categories_are_owner_scoped_and_aggregate_remains_shared(self):
        self.db.add(VenueVisit(user_id=self.other.user_id, venue_id=self.venue.venue_id, source='manual'))
        self.db.add(AwayDayReview(user_id=self.other.user_id, venue_id=self.venue.venue_id,
            atmosphere_score=2, pubs_score=2, getting_there_score=2, facilities_score=2,
            overall_score=2, recommend=False))
        self.db.commit()
        owner = main.get_my_grounds(SimpleNamespace(user_id=self.owner.user_id))[0]
        other = main.get_my_grounds(SimpleNamespace(user_id=self.other.user_id))[0]
        self.assertEqual(owner['venue_id'], self.venue.venue_id)
        self.assertEqual(owner['review']['atmosphere_score'], 8)
        self.assertEqual(other['review']['atmosphere_score'], 2)
        self.assertEqual(owner['community_terrace_rating'], other['community_terrace_rating'])
        self.assertEqual(owner['community_review_count'], 2)

    def test_edit_persists_and_retrieves_existing_record_without_duplicate(self):
        prior = self.db.query(AwayDayReview).one().review_id
        result = main.update_away_day_review(self.venue.venue_id,
            AwayDayReviewUpdate(atmosphere_score=9, pubs_score=8, getting_there_score=7, facilities_score=6, recommend=True),
            SimpleNamespace(user_id=self.owner.user_id))
        self.assertEqual(result.review_id, prior)
        self.assertEqual(main.get_my_grounds(SimpleNamespace(user_id=self.owner.user_id))[0]['review']['atmosphere_score'], 9)
        self.db.expire_all()
        self.assertEqual(self.db.query(AwayDayReview).count(), 1)

    def test_another_account_cannot_edit_owners_record(self):
        with self.assertRaises(HTTPException) as caught:
            main.update_away_day_review(self.venue.venue_id,
                AwayDayReviewUpdate(atmosphere_score=1), SimpleNamespace(user_id=self.other.user_id))
        self.assertEqual(caught.exception.status_code, 404)
        self.db.expire_all()
        self.assertEqual(self.db.query(AwayDayReview).one().atmosphere_score, 8)
