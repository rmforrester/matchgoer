"""Viewer permission and removal use existing ownership/storage boundaries."""
import unittest
from fastapi import HTTPException
from backend.tests import test_terraces_b1 as fixtures
from models import VenueVisit, TerracePhoto as Photo
import terraces_service as service

class FeedDeletionTests(unittest.TestCase):
    def setUp(self):fixtures.PhotoB1Tests.setUp(self)
    def tearDown(self):fixtures.PhotoB1Tests.tearDown(self)
    def submit(self, **kwargs):return fixtures.PhotoB1Tests.submit(self, **kwargs)

    def test_public_list_permission_is_viewer_specific_without_owner_id(self):
        self.submit(moderator=True)
        for viewer,expected in [(self.owner.user_id,True),(self.other.user_id,False),(None,False)]:
            photo=service.public_page(self.db,self.storage,viewer_user_id=viewer)['photos'][0]
            self.assertIs(photo['can_delete'],expected)
            self.assertNotIn('owner_user_id',photo)
            self.assertNotIn('submission_key',photo)

    def test_remove_and_repeat_preserve_attendance_and_other_photos(self):
        first=self.submit(label='one',moderator=True)['photo_id']
        second=self.submit(label='two',moderator=True)['photo_id']
        visit_id=self.visit.visit_id
        service.remove(self.db,self.storage,'Bearer synthetic',first)
        self.assertIsNotNone(self.db.get(VenueVisit,visit_id))
        self.assertEqual(self.db.get(Photo,second).status,'APPROVED')
        self.assertEqual([p['photo_id'] for p in service.public_page(self.db,self.storage,viewer_user_id=self.owner.user_id)['photos']],[second])
        service.remove(self.db,self.storage,'Bearer synthetic',first)
        self.assertIsNotNone(self.db.get(VenueVisit,visit_id))

    def test_other_supporter_cannot_delete_even_if_client_claims_permission(self):
        photo_id=self.submit(moderator=True)['photo_id']
        self.provider.subject=str(self.other.user_id)
        with self.assertRaises(HTTPException) as error:service.remove(self.db,self.storage,'Bearer synthetic',photo_id)
        self.assertEqual(error.exception.status_code,404)
        self.assertEqual(self.db.get(Photo,photo_id).status,'APPROVED')
        self.assertIsNotNone(self.db.get(VenueVisit,self.visit.visit_id))
