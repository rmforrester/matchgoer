"""Read-only receipt/HEAD monitor. Never downloads database or photo archives."""
from datetime import timedelta
import json
import re

import backup as b
from recovery_policy import timestamp
from recovery_acceptance import check as recovery_acceptance

PREFIX = 'supabase-recovery-v1/points/'
RECEIPT = re.compile(r'^supabase-recovery-v1/points/[0-9]{8}T[0-9]{6}Z-[a-f0-9]{8}/receipt.json$')


def health(s3, bucket, observed):
    rows = []
    count = 0
    for page in s3.get_paginator('list_objects_v2').paginate(Bucket=bucket, Prefix=PREFIX):
        count += 1
        if count > 10:
            raise b.BackupError('SUPABASE_MONITOR_LIST_LIMIT')
        rows.extend(o['Key'] for o in page.get('Contents', []) if RECEIPT.fullmatch(o['Key']))
    if not rows:
        return False, 'SUPABASE_RECOVERY_POINT_MISSING'
    key = max(rows)
    body = s3.get_object(Bucket=bucket, Key=key)['Body']
    try:
        raw = body.read(32769)
    finally:
        body.close()
    if len(raw) > 32768:
        return False, 'SUPABASE_RECEIPT_OVERSIZED'
    try:
        r = json.loads(raw)
    except (ValueError, TypeError):
        return False, 'SUPABASE_RECEIPT_INVALID'
    if not isinstance(r,dict) or r.get('version') != 1 or r.get('kind') != 'supabase-independent-recovery':
        return False, 'SUPABASE_RECEIPT_INVALID'
    try:
        stamp = timestamp(r.get('completed_at_utc'))
    except ValueError:
        return False, 'SUPABASE_RECEIPT_INVALID'
    if stamp > observed + timedelta(minutes=5) or observed-stamp > timedelta(hours=30):
        return False, 'SUPABASE_RECOVERY_POINT_STALE'
    if not r.get('data_exports_complete'):
        return False, 'SUPABASE_EXPORT_FAILED'
    expected = {'auth.dump.age', 'auth-verification.json.age', 'photos.tar.age'}
    artifacts = r.get('artifacts', [])
    prefix = key[:-len('receipt.json')]
    if not isinstance(artifacts,list) or any(not isinstance(a,dict)for a in artifacts):
        return False, 'SUPABASE_ARTIFACT_SET_INVALID'
    if {a.get('key') for a in artifacts} != {prefix+n for n in expected} or len(artifacts) != 3:
        return False, 'SUPABASE_ARTIFACT_SET_INVALID'
    for a in artifacts:
        if (not isinstance(a.get('sha256'),str) or not re.fullmatch(r'[0-9a-f]{64}', a['sha256'])
                or type(a.get('bytes')) is not int or a['bytes']<=0):
            return False, 'SUPABASE_ARTIFACT_RECEIPT_INVALID'
        try:
            b.verify_object(s3, bucket, a['key'], a['sha256'], a['bytes'], content=False)
        except b.BackupError:
            return False, 'SUPABASE_ARTIFACT_INTEGRITY_FAILED'
    return True, 'SUPABASE_RECOVERY_FRESH'


def main():
    observed = b.now()
    acceptance = recovery_acceptance(observed)
    checker_ok = True
    try:
        c = b.config(require_recipient=False)
        passed, reason = health(b.client(c), c['BACKUP_R2_BUCKET'], observed)
    except Exception as exc:
        response=getattr(exc,'response',{})
        error=response.get('Error',{}) if isinstance(response,dict) else {}
        missing=isinstance(error,dict) and str(error.get('Code'))in ('404','NoSuchKey','NotFound')
        passed=False
        reason='SUPABASE_RECOVERY_OBJECT_MISSING' if missing else 'SUPABASE_MONITOR_CHECK_FAILED'
        checker_ok=bool(missing)
    # Object health and completed recovery evidence are different assertions.
    # Never rewrite historical receipts or set complete_recovery on a new point.
    overall = passed and acceptance['passed']
    b.emit('SUPABASE_MONITOR_RESULT', passed=overall, reason=reason if not passed else acceptance['reason'],
           backup_creation_upload_health={'passed':passed if checker_ok else None,'reason':reason},
           checker_execution_health={'passed':checker_ok},
           recovery_acceptance=acceptance)
    if not passed:
        b.notify(reason, observed)
    elif not acceptance['passed']:
        b.notify(acceptance['reason'], observed)
    return 0 if overall else 1


if __name__ == '__main__':
    raise SystemExit(main())
