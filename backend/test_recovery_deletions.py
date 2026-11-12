"""No database/network access: verify mandatory journaling before physical purge."""
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import Mock
import sys
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).parent))
import recovery_deletions as r


class StorageUnavailable(Exception):
    pass


@pytest.fixture(autouse=True)
def isolated(monkeypatch):
    monkeypatch.setenv('RECOVERY_DELETION_CAPTURE_ENABLED', 'true')
    monkeypatch.setitem(sys.modules, 'terraces_storage', SimpleNamespace(StorageUnavailable=StorageUnavailable))
    monkeypatch.setattr(r, 'warn', Mock())


def event():
    return SimpleNamespace(event_id=7, created_at=datetime.now(timezone.utc),
                           payload={'display_key':'photos/'+'a'*32+'/display.jpg',
                                    'thumbnail_key':'photos/'+'a'*32+'/thumbnail.jpg'})


def test_cascade_requires_durable_receipt_before_delete(monkeypatch):
    e = event(); writer = Mock(return_value={'durable':True,'key':'opaque','sha256':'h'})
    monkeypatch.setattr(r, 'write', writer)
    r.before_cascade_photo_purge(e)
    assert writer.call_args.args[0]['object_keys'] == [e.payload['display_key'], e.payload['thumbnail_key']]
    assert e.payload['recovery_journal'] == {'key':'opaque','sha256':'h'}


@pytest.mark.parametrize('outcome', [RuntimeError(), {'durable':False}])
def test_journal_outage_defers_physical_purge(monkeypatch, outcome):
    writer = Mock(side_effect=outcome) if isinstance(outcome, Exception) else Mock(return_value=outcome)
    monkeypatch.setattr(r, 'write', writer)
    with pytest.raises(StorageUnavailable):
        r.before_cascade_photo_purge(event())
    r.warn.assert_called_once()


def test_feature_flag_off_preserves_original_behavior(monkeypatch):
    monkeypatch.delenv('RECOVERY_DELETION_CAPTURE_ENABLED')
    writer = Mock(); monkeypatch.setattr(r, 'write', writer)
    r.before_cascade_photo_purge(event())
    writer.assert_not_called()


def test_rollback_flag_never_bypasses_established_protection(monkeypatch):
    monkeypatch.delenv('RECOVERY_DELETION_CAPTURE_ENABLED')
    monkeypatch.setenv('RECOVERY_DELETION_PROTECTION_REQUIRED','true')
    with pytest.raises(StorageUnavailable):
        r.before_cascade_photo_purge(event())
    with pytest.raises(StorageUnavailable):
        r.before_photo_purge(None,None)


def test_guest_scope_never_modified(monkeypatch):
    row = SimpleNamespace(request_type='guest_history', record_scope={'protected':[1]})
    writer = Mock(); monkeypatch.setattr(r, 'write', writer)
    r.capture_account_request(None, row)
    writer.assert_not_called()
    assert row.record_scope == {'protected':[1]}


def test_account_request_preserved_and_retryable_on_outage(monkeypatch):
    field = Mock(); field.__eq__ = Mock(return_value=True)
    monkeypatch.setitem(sys.modules, 'models', SimpleNamespace(UserIdentity=SimpleNamespace(user_id=field,user_identity_id=1)))
    db = Mock(); db.query.return_value.filter.return_value.order_by.return_value = [
        SimpleNamespace(issuer='https://synthetic.supabase.co/auth/v1', subject='00000000-0000-0000-0000-000000000001')]
    row = SimpleNamespace(request_type='account', record_scope={}, user_id=1, request_id='synthetic',
                          requested_at=datetime.now(timezone.utc))
    monkeypatch.setattr(r, 'write', Mock(side_effect=RuntimeError()))
    r.capture_account_request(db, row)
    assert row.record_scope['recovery_journal'] == {'durable':False,'retry_pending':True}
    monkeypatch.setattr(r, 'write', Mock(return_value={'durable':True,'key':'opaque','sha256':'h'}))
    r.capture_account_request(db, row)
    assert row.record_scope['recovery_journal']['durable'] is True
