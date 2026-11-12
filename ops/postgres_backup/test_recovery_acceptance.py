from pathlib import Path
from datetime import datetime,timezone,timedelta
import shutil
import json
import recovery_acceptance as m

NOW=datetime(2026,11,12,tzinfo=timezone.utc)


def test_original_founder_receipt_and_deletion_coverage_chain_pass():
    result=m.check(NOW)
    assert result['passed'] and result['mandatory_journal_replay']
    assert result['current_backup_restored'] is False
    assert result['current_restore_requires_fresh_coverage_and_replay']


def test_missing_evidence_fails_closed(tmp_path):
    assert m.check(NOW,evidence_dir=tmp_path)['reason']=='RECOVERY_ACCEPTANCE_EVIDENCE_MISSING'


def test_stale_original_evidence_is_not_accepted():
    result=m.check(datetime(2027,3,1,tzinfo=timezone.utc))
    assert not result['passed'] and result['reason']=='RECOVERY_ACCEPTANCE_EVIDENCE_STALE'


def test_future_cutoff_not_accepted():
    assert not m.check(datetime(2026,11,10,tzinfo=timezone.utc))['passed']


def test_manual_success_flag_cannot_replace_original_receipt(tmp_path):
    shutil.copytree(m.ROOT/'recovery_acceptance_evidence',tmp_path/'evidence')
    p=tmp_path/'evidence/founder-deletion-safe-restore-receipt.json'
    p.write_text(json.dumps({'passed':True,'mandatory_journal_replay':True}))
    assert not m.check(NOW,evidence_dir=p.parent)['passed']


def test_missing_journal_coverage_evidence_is_rejected(tmp_path):
    shutil.copytree(m.ROOT/'recovery_acceptance_evidence',tmp_path/'evidence')
    (tmp_path/'evidence/fresh-readonly-check.json').unlink()
    assert not m.check(NOW,evidence_dir=tmp_path/'evidence')['passed']


def test_changed_restore_guards_invalidate_acceptance(tmp_path):
    for name in ['mandatory_restore.py','restore_check.py','deletion_suppression.py','recovery_policy.py']:
        shutil.copyfile(m.ROOT/name,tmp_path/name)
    (tmp_path/'mandatory_restore.py').write_text('# bypass suppression')
    result=m.check(NOW,code_dir=tmp_path)
    assert not result['passed'] and result['reason']=='RECOVERY_ACCEPTANCE_RESTORE_CODE_CHANGED'
