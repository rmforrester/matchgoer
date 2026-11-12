"""Encrypted, append-only suppression records; never deletes production data.

Founder approved a 100-day supported point limit and 120-day journal retention.
Unknown legacy copies remain excluded. No indefinite journal retention.
"""
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import tempfile

try:
    from . import backup as b
    from .supabase_recovery import PREFIX, RecoveryError, encrypt_json, OBJECT
except ImportError:
    import backup as b
    from supabase_recovery import PREFIX, RecoveryError, encrypt_json, OBJECT

PROPOSED_MAX_POINT_AGE_DAYS = 100
PROPOSED_JOURNAL_DAYS = 120
PROPOSED_CLEANUP_MARGIN_DAYS = 20


def validate_event(event):
    if not isinstance(event, dict) or event.get('kind') not in ('photo', 'account'):
        raise RecoveryError('SUPPRESSION_EVENT_INVALID')
    allowed = {'kind', 'event_id', 'occurred_at_utc', 'user_id', 'photo_id', 'object_keys', 'identities', 'phase'}
    if set(event) - allowed or not event.get('event_id') or not event.get('occurred_at_utc'):
        raise RecoveryError('SUPPRESSION_EVENT_INVALID')
    stamp = datetime.fromisoformat(event['occurred_at_utc'])
    if stamp.tzinfo is None:
        raise RecoveryError('SUPPRESSION_EVENT_TIME_INVALID')
    if event.get('user_id') is not None and (type(event['user_id']) is not int or event['user_id'] <= 0):
        raise RecoveryError('SUPPRESSION_EVENT_OWNER_INVALID')
    if event['kind'] == 'photo':
        if event.get('photo_id') is not None and type(event['photo_id']) is not int:
            raise RecoveryError('SUPPRESSION_PHOTO_IDENTITY_INVALID')
        if len(event.get('object_keys', [])) != 2 or len(set(event['object_keys'])) != 2:
            raise RecoveryError('SUPPRESSION_PHOTO_IDENTITY_INVALID')
        if any(not OBJECT.fullmatch(k) for k in event['object_keys']):
            raise RecoveryError('SUPPRESSION_PHOTO_KEY_INVALID')
    else:
        from uuid import UUID
        if event.get('phase') not in ('requested', 'erasure_authorized'):
            raise RecoveryError('SUPPRESSION_ACCOUNT_PHASE_REQUIRED')
        if not event.get('user_id') or not event.get('identities'):
            raise RecoveryError('SUPPRESSION_ACCOUNT_IDENTITY_REQUIRED')
        for i in event['identities']:
            if set(i) != {'issuer', 'subject'} or not i['issuer'].startswith('https://'):
                raise RecoveryError('SUPPRESSION_ACCOUNT_IDENTITY_INVALID')
            UUID(i['subject'])
    return event


def append(event, env=os.environ):
    """Return only after immutable encrypted record + ciphertext read-back succeed."""
    event = validate_event(event)
    c = b.config(env)
    s3, bucket = b.client(c), c['BACKUP_R2_BUCKET']
    encoded = json.dumps(event, sort_keys=True, separators=(',', ':')).encode()
    fingerprint = hashlib.sha256(encoded).hexdigest()
    prefix = PREFIX + 'deletions/' + fingerprint + '/'
    key = prefix + 'suppression.json.age'
    try:
        head = s3.head_object(Bucket=bucket, Key=key)
    except Exception as exc:
        if not b.not_found(exc):
            raise RecoveryError('SUPPRESSION_STORAGE_UNAVAILABLE') from None
    else:
        metadata = head.get('Metadata', {})
        if metadata.get('event_digest') != fingerprint or not metadata.get('sha256'):
            raise RecoveryError('SUPPRESSION_EXISTING_RECORD_CONFLICT')
        b.verify_object(s3, bucket, key, metadata['sha256'], head['ContentLength'])
        receipt_key = prefix + 'receipt.json'
        try:
            response = s3.get_object(Bucket=bucket, Key=receipt_key)['Body']
        except Exception as exc:
            if not b.not_found(exc):
                raise RecoveryError('SUPPRESSION_RECEIPT_UNAVAILABLE') from None
            receipt = {'version': 1, 'key': key, 'sha256': metadata['sha256'], 'bytes': head['ContentLength'],
                       'captured_at_utc': metadata.get('captured_at_utc'), 'verified': True,
                       'retention_policy': '120_DAY_JOURNAL_100_DAY_SUPPORTED_POINT_LIMIT'}
            s3.put_object(Bucket=bucket, Key=receipt_key, Body=json.dumps(receipt).encode(),
                          ContentType='application/json', StorageClass='STANDARD', IfNoneMatch='*')
        else:
            try: receipt = json.loads(response.read(8192))
            finally: response.close()
            if receipt.get('sha256') != metadata['sha256'] or receipt.get('verified') is not True:
                raise RecoveryError('SUPPRESSION_RECEIPT_CONFLICT')
        return {'durable': True, 'key': key, 'sha256': metadata['sha256'], 'idempotent': True}
    with tempfile.TemporaryDirectory(prefix='matchgoer-suppression-ciphertext-') as td:
        os.chmod(td, 0o700)
        file = Path(td) / 'suppression.json.age'
        captured = b.now().isoformat()
        encrypt_json({'version': 1, 'source': b.SOURCE, 'captured_at_utc': captured,
                      'event': event, 'restore_suppression': True}, file, c['BACKUP_AGE_RECIPIENT'])
        h, size = b.digest(file), file.stat().st_size
        with file.open('rb') as stream:
            s3.put_object(Bucket=bucket, Key=key, Body=stream, ContentType='application/octet-stream',
                          StorageClass='STANDARD', Metadata={'sha256': h, 'event_digest': fingerprint, 'captured_at_utc': captured}, IfNoneMatch='*')
        b.verify_object(s3, bucket, key, h, size)
        receipt = {'version': 1, 'key': key, 'sha256': h, 'bytes': size, 'captured_at_utc': captured,
                   'verified': True, 'retention_policy': '120_DAY_JOURNAL_100_DAY_SUPPORTED_POINT_LIMIT'}
        s3.put_object(Bucket=bucket, Key=prefix + 'receipt.json', Body=json.dumps(receipt).encode(),
                      ContentType='application/json', StorageClass='STANDARD', IfNoneMatch='*')
    return {'durable': True, 'key': key, 'sha256': h, 'idempotent': False}


def retirement_decision(event_time, captured_time, points, observed, approved=False, inventory_complete=False):
    """Planning/purge preflight only. Unknown/offline retained copies fail closed."""
    if not approved:
        return {'may_prune': False, 'reason': 'BOUNDED_POLICY_NOT_APPROVED'}
    if not inventory_complete:
        return {'may_prune': False, 'reason': 'RECOVERY_COPY_INVENTORY_INCOMPLETE'}
    if observed < captured_time + timedelta(days=PROPOSED_JOURNAL_DAYS):
        return {'may_prune': False, 'reason': 'JOURNAL_WINDOW_NOT_EXPIRED'}
    for point in points:
        if not point.get('inventory_verified'):
            return {'may_prune': False, 'reason': 'RECOVERY_COPY_INVENTORY_INCOMPLETE'}
        snapshot = datetime.fromisoformat(point['snapshot_at_utc'])
        if snapshot > event_time:
            continue
        if not point.get('retired_and_not_restorable') or not point.get('all_copies_accounted_for'):
            return {'may_prune': False, 'reason': 'OLDER_RECOVERY_COPY_STILL_USABLE'}
        verified = datetime.fromisoformat(point['retirement_verified_at_utc'])
        if observed < verified + timedelta(days=PROPOSED_CLEANUP_MARGIN_DAYS):
            return {'may_prune': False, 'reason': 'RETIREMENT_SAFETY_MARGIN_NOT_EXPIRED'}
    return {'may_prune': True, 'reason': 'ALL_PRIOR_POINTS_VERIFIABLY_RETIRED'}


def restore_age_guard(snapshot_time, observed, policy_approved=False):
    if not policy_approved:
        raise RecoveryError('BOUNDED_RESTORE_POLICY_NOT_APPROVED')
    if snapshot_time.tzinfo is None or snapshot_time > observed + timedelta(minutes=5):
        raise RecoveryError('RECOVERY_POINT_TIME_INVALID')
    if observed - snapshot_time > timedelta(days=PROPOSED_MAX_POINT_AGE_DAYS):
        raise RecoveryError('RECOVERY_POINT_EXCEEDS_BOUNDED_ELIGIBILITY')
    return True
