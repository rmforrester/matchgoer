"""Profile regression: explicit visit origin, canonical counts and owner isolation."""
from datetime import datetime, timezone
import unittest

from sqlalchemy import func
from sqlalchemy.exc import InvalidRequestError
from sqlalchemy.orm import Session

from database import SessionLocal
from identity import ResolvedIdentity
from main import get_profile
from models import User, UserProfile, Venue, VenueVisit


class ProfileGroundCountTests(unittest.TestCase):
    def setUp(self):
        self.db = SessionLocal()
        self.users = [User(is_anonymous=False, account_status='registered',
                           registered_at=datetime.now(timezone.utc)) for _ in range(2)]
        self.db.add_all(self.users)
        self.db.flush()
        self.db.add_all([UserProfile(user_id=u.user_id, display_name='Synthetic profile')
                         for u in self.users])
        self.venues = [Venue(name='Synthetic profile ground', city='Test', country='Test',
                             latitude=0, longitude=0) for _ in range(3)]
        self.db.add_all(self.venues)
        self.db.flush()
        self.venues[1].canonical_venue_id = self.venues[0].venue_id
        self.venues[1].equivalence_source = 'Synthetic regression: same physical ground'
        self.db.commit()
        self.owner = self.users[0].user_id
        self.other = self.users[1].user_id
        self.venue_ids = [v.venue_id for v in self.venues]

    def tearDown(self):
        self.db.rollback()
        ids = [self.owner, self.other]
        self.db.query(VenueVisit).filter(VenueVisit.user_id.in_(ids)).delete(synchronize_session=False)
        self.db.query(UserProfile).filter(UserProfile.user_id.in_(ids)).delete(synchronize_session=False)
        self.db.query(User).filter(User.user_id.in_(ids)).delete(synchronize_session=False)
        self.db.query(Venue).filter(Venue.venue_id.in_(self.venue_ids)).update(
            {Venue.canonical_venue_id: None, Venue.equivalence_source: None}, synchronize_session=False)
        self.db.query(Venue).filter(Venue.venue_id.in_(self.venue_ids)).delete(synchronize_session=False)
        self.db.commit()
        self.db.close()

    def profile(self, owner):
        return get_profile(identity=ResolvedIdentity(owner, 'registered', True, 'bearer'))

    def test_original_unanchored_query_cannot_compile(self):
        with Session() as db:
            query = db.query(func.count(func.distinct(func.coalesce(
                Venue.canonical_venue_id, VenueVisit.venue_id)))).join(
                    Venue, Venue.venue_id == VenueVisit.venue_id).filter(VenueVisit.user_id == -1)
            with self.assertRaises(InvalidRequestError):
                query.statement.compile()

    def test_new_profile_without_visits_returns_zero(self):
        result = self.profile(self.owner)
        self.assertEqual(result['grounds_visited'], 0)
        self.assertEqual(result['user_id'], self.owner)
        self.assertTrue(result['profile_complete'])

    def test_canonical_aliases_and_repeat_visits_count_once_per_owner(self):
        for uid, venue in [(self.owner, self.venue_ids[0]),
                           (self.owner, self.venue_ids[0]),
                           (self.owner, self.venue_ids[1]),
                           (self.other, self.venue_ids[2])]:
            self.db.add(VenueVisit(user_id=uid, venue_id=venue, source='manual'))
        self.db.commit()
        self.assertEqual(self.profile(self.owner)['grounds_visited'], 1)
        self.assertEqual(self.profile(self.other)['grounds_visited'], 1)

    def test_missing_profile_and_missing_identity_remain_empty(self):
        self.db.query(UserProfile).filter_by(user_id=self.owner).delete()
        self.db.commit()
        self.assertIsNone(self.profile(self.owner))
        self.assertIsNone(get_profile(identity=None))
