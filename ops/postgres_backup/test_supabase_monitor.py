import io
import json
from datetime import datetime, timezone, timedelta
from unittest.mock import Mock
import pytest
import check_supabase as m

NOW = datetime(2026,11,12,tzinfo=timezone.utc)
PREFIX = m.PREFIX+'20261111T000000Z-aaaaaaaa/'


def storage(**changes):
    receipt = dict(version=1, kind='supabase-independent-recovery', completed_at_utc=NOW.isoformat(),
                   data_exports_complete=True, complete_recovery=False,
                   artifacts=[dict(key=PREFIX+n, bytes=123, sha256='a'*64) for n in
                              ('auth.dump.age','auth-verification.json.age','photos.tar.age')])
    receipt.update(changes)
    client = Mock()
    client.get_paginator.return_value.paginate.return_value = [{'Contents':[{'Key':PREFIX+'receipt.json'}]}]
    client.get_object.return_value = {'Body':io.BytesIO(json.dumps(receipt).encode())}
    client.head_object.return_value = {'ContentLength':123,'Metadata':{'sha256':'a'*64}}
    return client


def test_healthy_checks_only_receipt_and_head():
    c = storage()
    assert m.health(c,'synthetic',NOW) == (True,'SUPABASE_RECOVERY_FRESH')
    c.get_object.assert_called_once_with(Bucket='synthetic',Key=PREFIX+'receipt.json')
    assert c.head_object.call_count == 3
    c.delete_object.assert_not_called(); c.put_object.assert_not_called()


@pytest.mark.parametrize('changes,code', [
    ({'completed_at_utc':(NOW-timedelta(hours=31)).isoformat()},'STALE'),
    ({'data_exports_complete':False},'EXPORT_FAILED'),
    ({'artifacts':[]},'ARTIFACT_SET_INVALID')])
def test_failed_or_partial_backup_never_healthy(changes,code):
    passed,reason=m.health(storage(**changes),'synthetic',NOW)
    assert not passed and reason.endswith(code)


def test_success_emits_no_email(monkeypatch):
    monkeypatch.setattr(m.b,'config',lambda **kw:{'BACKUP_R2_BUCKET':'synthetic'})
    monkeypatch.setattr(m.b,'client',lambda c:storage())
    monkeypatch.setattr(m.b,'now',lambda:NOW)
    notify=Mock();monkeypatch.setattr(m.b,'notify',notify)
    assert m.main()==0
    notify.assert_not_called()


def test_failure_emits_exception_only_alert(monkeypatch):
    monkeypatch.setattr(m.b,'config',lambda **kw:{'BACKUP_R2_BUCKET':'synthetic'})
    monkeypatch.setattr(m.b,'client',lambda c:storage(data_exports_complete=False))
    monkeypatch.setattr(m.b,'now',lambda:NOW)
    notify=Mock();monkeypatch.setattr(m.b,'notify',notify)
    assert m.main()==1
    notify.assert_called_once_with('SUPABASE_EXPORT_FAILED',NOW)


def test_historical_false_acceptance_flag_does_not_claim_new_restore_or_fail_object_health():
    assert m.health(storage(complete_recovery=False),'synthetic',NOW)==(True,'SUPABASE_RECOVERY_FRESH')


def test_invalid_acceptance_is_distinct_from_backup_and_checker_health(monkeypatch):
    monkeypatch.setattr(m.b,'config',lambda **kw:{'BACKUP_R2_BUCKET':'synthetic'})
    monkeypatch.setattr(m.b,'client',lambda c:storage())
    monkeypatch.setattr(m.b,'now',lambda:NOW)
    monkeypatch.setattr(m,'recovery_acceptance',lambda observed:{'passed':False,'reason':'RECOVERY_ACCEPTANCE_EVIDENCE_MISSING'})
    notify=Mock();emit=Mock();monkeypatch.setattr(m.b,'notify',notify);monkeypatch.setattr(m.b,'emit',emit)
    assert m.main()==1
    notify.assert_called_once_with('RECOVERY_ACCEPTANCE_EVIDENCE_MISSING',NOW)
    assert emit.call_args.kwargs['backup_creation_upload_health']['passed']
    assert emit.call_args.kwargs['checker_execution_health']['passed']
    assert not emit.call_args.kwargs['recovery_acceptance']['passed']


def test_corrupt_object_is_backup_integrity_failure_not_checker_unavailability():
    c=storage();c.head_object.return_value={'ContentLength':124,'Metadata':{'sha256':'a'*64}}
    assert m.health(c,'synthetic',NOW)==(False,'SUPABASE_ARTIFACT_INTEGRITY_FAILED')


def test_checker_access_failure_means_backup_health_unknown(monkeypatch):
    def failed_config(**kwargs):raise RuntimeError('synthetic credentials unavailable')
    monkeypatch.setattr(m.b,'config',failed_config);monkeypatch.setattr(m.b,'now',lambda:NOW)
    notify=Mock();emit=Mock();monkeypatch.setattr(m.b,'notify',notify);monkeypatch.setattr(m.b,'emit',emit)
    assert m.main()==1
    result=emit.call_args.kwargs
    assert result['backup_creation_upload_health']['passed']is None
    assert not result['checker_execution_health']['passed']


def test_confirmed_missing_object_is_not_mislabelled_checker_failure(monkeypatch):
    missing=RuntimeError('synthetic object missing');missing.response={'Error':{'Code':'NoSuchKey'}}
    monkeypatch.setattr(m.b,'config',lambda **kw:{'BACKUP_R2_BUCKET':'synthetic'})
    monkeypatch.setattr(m.b,'client',lambda config:Mock())
    def absent(*args):raise missing
    monkeypatch.setattr(m,'health',absent);monkeypatch.setattr(m.b,'now',lambda:NOW)
    emit=Mock();monkeypatch.setattr(m.b,'emit',emit);monkeypatch.setattr(m.b,'notify',Mock())
    assert m.main()==1
    result=emit.call_args.kwargs
    assert result['reason']=='SUPABASE_RECOVERY_OBJECT_MISSING'
    assert result['backup_creation_upload_health']['passed']is False
    assert result['checker_execution_health']['passed']
