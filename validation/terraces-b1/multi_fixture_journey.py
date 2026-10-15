"""Synthetic local PostgreSQL and fake object storage only; no hosted accounts."""
import unittest
from unittest.mock import patch
from datetime import datetime,timezone
from uuid import uuid4
from models import Venue,VenueVisit,Fixture,TerracePhoto,TerracePhotoEvent
from fastapi import HTTPException
from backend.tests import test_terraces_b1 as fixtures
import terraces_service as service

class MultiFixtureJourney(unittest.TestCase):
    setUp=fixtures.PhotoB1Tests.setUp
    tearDown=fixtures.PhotoB1Tests.tearDown
    submit=fixtures.PhotoB1Tests.submit

    def test_two_accounts_multiple_fixtures_and_historical_visit_complete_journey(self):
        other_ground=Venue(name='Synthetic second canonical ground',country='Test')
        self.db.add(other_ground);self.db.flush()
        fixtures=[Fixture(fixture_id=910000010+i,home_team='Synthetic home',away_team='Synthetic away',venue_id=venue,fixture_date=datetime(2026,8,28,tzinfo=timezone.utc),status='FT') for i,venue in enumerate((self.venue.venue_id,other_ground.venue_id))]
        self.db.add_all(fixtures);self.db.flush()
        visits=[VenueVisit(user_id=self.owner.user_id,venue_id=self.venue.venue_id,fixture_id=fixtures[0].fixture_id,source='fixture_confirmation'),VenueVisit(user_id=self.owner.user_id,venue_id=other_ground.venue_id,fixture_id=fixtures[1].fixture_id,source='fixture_confirmation'),VenueVisit(user_id=self.other.user_id,venue_id=other_ground.venue_id,fixture_id=fixtures[1].fixture_id,source='fixture_confirmation')]
        self.db.add_all(visits);self.db.flush()
        historical=self.visit
        with patch.dict('os.environ',{'TERRACES_UPLOAD_USER_IDS':f'{self.owner.user_id},{self.other.user_id}'}):
            for index,(actor,visit) in enumerate([(self.owner,visits[0]),(self.owner,visits[1]),(self.other,visits[2]),(self.owner,historical)]):
                self.provider.subject=str(actor.user_id);self.visit=visit
                photos=[self.submit(f'journey-{index}-{n}') for n in range(3)]
                retry_key=str(uuid4())
                with self.assertRaises(HTTPException) as quota:self.submit(f'blocked-fourth-{index}',retry_key)
                self.assertEqual(quota.exception.status_code,409)
                if actor==self.other:
                    with self.assertRaises(HTTPException) as moderation:service.approve(self.db,'Bearer synthetic',photos[0]['photo_id'])
                    self.assertEqual(moderation.exception.status_code,403)
                self.provider.subject=str(self.owner.user_id)
                service.approve(self.db,'Bearer synthetic',photos[0]['photo_id'])
                self.provider.subject=str(actor.user_id)
                self.assertEqual(service.remove(self.db,self.storage,'Bearer synthetic',photos[0]['photo_id'])['status'],'REMOVED')
                replacement=self.submit(f'different-replacement-{index}',retry_key)
                self.assertEqual(self.submit(f'different-replacement-{index}',retry_key),replacement)
                self.assertEqual(self.db.query(TerracePhoto).filter(TerracePhoto.visit_id==visit.visit_id,TerracePhoto.status.in_(('PENDING','APPROVED'))).count(),3)
                for result in [*photos[1:],replacement]:service.remove(self.db,self.storage,'Bearer synthetic',result['photo_id'])
                self.assertEqual(self.db.query(TerracePhoto).filter(TerracePhoto.visit_id==visit.visit_id,TerracePhoto.status.in_(('PENDING','APPROVED'))).count(),0)
                self.assertEqual(self.db.query(TerracePhoto).filter_by(visit_id=visit.visit_id).count(),4)
            self.provider.subject=str(self.other.user_id);self.visit=visits[0]
            with self.assertRaises(HTTPException) as ownership:self.submit('cross-account')
            self.assertEqual(ownership.exception.status_code,404)
            self.assertEqual(self.storage.objects,{})
            self.assertEqual(self.db.query(TerracePhoto).count(),16)
            self.assertEqual(self.db.query(TerracePhotoEvent).filter_by(event_type='REMOVAL_REQUESTED').count(),16)
