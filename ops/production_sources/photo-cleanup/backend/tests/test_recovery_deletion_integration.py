"""Synthetic service-boundary checks; no database/network/storage mutation."""
import unittest
from types import SimpleNamespace
from datetime import datetime, timezone
from unittest.mock import Mock, patch
from terraces_storage import StorageUnavailable
import terraces_service as service
import recovery_deletions as recovery


class DeletionProtectionIntegration(unittest.TestCase):
    def photo(self):
        return SimpleNamespace(photo_id=123,owner_user_id=456,status='APPROVED',
            published_at=datetime.now(timezone.utc),removed_at=None,rejected_at=None,
            storage_deleted_at=None,dispute_reason=None,display_key='synthetic-display',
            thumbnail_key='synthetic-thumbnail')

    def test_unpublication_survives_journal_failure_without_physical_delete(self):
        db,storage=Mock(),Mock();photo=self.photo();db.get.return_value=photo
        with patch.object(service,'require_verified_account',return_value=SimpleNamespace(user_id=456)),\
             patch.object(service,'lock',return_value=photo),patch.object(service,'event'),\
             patch.object(recovery,'before_photo_purge',side_effect=StorageUnavailable()):
            result=service.remove(db,storage,'synthetic',123)
        self.assertEqual(photo.status,'REMOVED');self.assertIsNone(photo.published_at)
        self.assertEqual(result['public_visibility'],'removed')
        self.assertEqual(result['physical_cleanup'],'pending')
        db.commit.assert_called_once();db.rollback.assert_called_once()
        storage.delete.assert_not_called()

    def test_verified_capture_precedes_both_physical_deletes(self):
        db,storage=Mock(),Mock();photo=self.photo();photo.status='REMOVED'
        order=[]
        with patch.object(service,'lock',return_value=photo),patch.object(service,'event'),\
             patch.object(recovery,'before_photo_purge',side_effect=lambda *a:order.append('journal')):
            storage.delete.side_effect=lambda key:order.append('delete')
            self.assertTrue(service.purge_photo(db,storage,123))
        self.assertEqual(order,['journal','delete','delete'])
        self.assertIsNotNone(photo.storage_deleted_at)

    def test_other_supporter_cannot_remove_photo(self):
        db,storage=Mock(),Mock();photo=self.photo()
        with patch.object(service,'require_verified_account',return_value=SimpleNamespace(user_id=999)),\
             patch.object(service,'lock',return_value=photo):
            with self.assertRaises(Exception) as e:service.remove(db,storage,'synthetic',123)
        self.assertEqual(e.exception.status_code,404)
        self.assertEqual(photo.status,'APPROVED');storage.delete.assert_not_called()
