"""Verify a pinned completed restore, never certify a backup's future restore."""
import hashlib
import json
from pathlib import Path
from datetime import timedelta
try:
    from .recovery_policy import timestamp, MAX_POINT_DAYS
except ImportError:
    from recovery_policy import timestamp, MAX_POINT_DAYS

EVIDENCE_SHA256 = '009f3e2e0475664f7938a4bc2f44842112a3ce70eb52018acc0b520aebe4b1af'
ROOT = Path(__file__).resolve().parent


def check(observed, evidence_dir=None, code_dir=None):
    """No environment bypass, key, archive, network, restore or success switch."""
    evidence_dir = Path(evidence_dir) if evidence_dir is not None else ROOT/'recovery_acceptance_evidence'
    code_dir = Path(code_dir) if code_dir is not None else ROOT
    try:
        manifest_path = evidence_dir/'manifest.json'
        if not manifest_path.is_file():
            return dict(passed=False, reason='RECOVERY_ACCEPTANCE_EVIDENCE_MISSING')
        digest = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
        if digest(manifest_path) != EVIDENCE_SHA256:
            raise ValueError()
        manifest = json.loads(manifest_path.read_text(encoding='utf-8-sig'))
        if manifest['version'] != 1:
            raise ValueError()
        files = {}
        for name, expected in manifest['files'].items():
            if Path(name).name != name or digest(evidence_dir/name) != expected:
                raise ValueError()
            files[name] = json.loads((evidence_dir/name).read_text(encoding='utf-8-sig'))
        for name, expected in manifest['restore_code'].items():
            # Git/Windows line-ending conversion is not a restore-code change.
            code_digest=hashlib.sha256((code_dir/name).read_bytes().replace(b'\r\n',b'\n')).hexdigest()
            if Path(name).name != name or code_digest != expected:
                return dict(passed=False, reason='RECOVERY_ACCEPTANCE_RESTORE_CODE_CHANGED')
        receipt = files['founder-deletion-safe-restore-receipt.json']
        selected = files['selected-set-eligibility.json']
        coverage = files['fresh-readonly-check.json']
        attestation = files['founder-attestation.json']
        cutoff = timestamp(manifest['cutoff_utc'])
        if any(timestamp(v) != cutoff for v in (
                receipt['cutoff_utc'], selected['restore_cutoff_utc'], coverage['cutoff_utc'])):
            raise ValueError()
        if receipt['inventory_sha256'] != manifest['inventory_sha256']:
            raise ValueError()
        if not all(receipt.get(k) is True for k in ('passed', 'mandatory_journal_replay',
                'all_row_fingerprints_match', 'fingerprints_are_pre_suppression', 'isolated_validation_only',
                'session_reauthentication_required')):
            raise ValueError()
        if not all(receipt.get(k) is False for k in ('production_connected',
                'private_key_printed_or_copied', 'cutover_authorised')):
            raise ValueError()
        if (receipt['tables_verified'], receipt['auth_tables_verified'], receipt['photo_objects_retained']) != (44,18,14):
            raise ValueError()
        if not (coverage['selected_set_deletion_coverage_eligible'] is True
                and coverage['protection_hook_source_and_configuration_unchanged'] is True
                and coverage['read_only'] is True and coverage['tls'] is True
                and all(v == 0 for v in coverage['checks'].values())
                and selected['mandatory_replay_required_even_with_zero_events'] is True
                and timestamp(attestation['from_utc']) <= timestamp(selected['coverage_from_utc']) <= cutoff):
            raise ValueError()
        identities=coverage['identity_check']
        if not (identities['available'] is True
                and identities['auth_users']==identities['exact_bindings_matched']==selected['auth_bindings_expected']==14
                and identities['preserved_orphan_bindings']==selected['orphan_bindings_preserved']==3
                and coverage['railway_identity_mappings']==17
                and receipt['journal_events_replayed']==selected['required_post_point_deletion_events']):
            raise ValueError()
        if cutoff > observed + timedelta(minutes=5):
            raise ValueError()
        if observed - cutoff > timedelta(days=MAX_POINT_DAYS):
            return dict(passed=False, reason='RECOVERY_ACCEPTANCE_EVIDENCE_STALE', cutoff_utc=cutoff.isoformat())
        return dict(passed=True, reason='DELETION_SAFE_RESTORE_EVIDENCE_VERIFIED',
                    evidence_sha256=EVIDENCE_SHA256, cutoff_utc=cutoff.isoformat(),
                    mandatory_journal_replay=True, current_backup_restored=False,
                    current_restore_requires_fresh_coverage_and_replay=True)
    except (OSError, ValueError, KeyError, TypeError):
        return dict(passed=False, reason='RECOVERY_ACCEPTANCE_EVIDENCE_INVALID')
