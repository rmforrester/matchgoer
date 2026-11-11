"""Read-only receipt/HEAD monitor. Never downloads database or photo archives."""
from datetime import timedelta
import json
import re

import backup as b
from recovery_policy import timestamp

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
    r = json.loads(raw)
    if r.get('version') != 1 or r.get('kind') != 'supabase-independent-recovery':
        return False, 'SUPABASE_RECEIPT_INVALID'
    stamp = timestamp(r.get('completed_at_utc'))
    if stamp > observed + timedelta(minutes=5) or observed-stamp > timedelta(hours=30):
        return False, 'SUPABASE_RECOVERY_POINT_STALE'
    if not r.get('data_exports_complete'):
        return False, 'SUPABASE_EXPORT_FAILED'
    expected = {'auth.dump.age', 'auth-verification.json.age', 'photos.tar.age'}
    artifacts = r.get('artifacts', [])
    prefix = key[:-len('receipt.json')]
    if {a.get('key') for a in artifacts} != {prefix+n for n in expected} or len(artifacts) != 3:
        return False, 'SUPABASE_ARTIFACT_SET_INVALID'
    for a in artifacts:
        if not re.fullmatch(r'[0-9a-f]{64}', a.get('sha256', '')) or type(a.get('bytes')) is not int:
            return False, 'SUPABASE_ARTIFACT_RECEIPT_INVALID'
        b.verify_object(s3, bucket, a['key'], a['sha256'], a['bytes'], content=False)
    if r.get('complete_recovery') is not True:
        return False, 'SUPABASE_RECOVERY_ACCEPTANCE_INCOMPLETE'
    return True, 'SUPABASE_RECOVERY_FRESH'


def main():
    observed = b.now()
    try:
        c = b.config(require_recipient=False)
        passed, reason = health(b.client(c), c['BACKUP_R2_BUCKET'], observed)
    except Exception:
        passed, reason = False, 'SUPABASE_MONITOR_CHECK_FAILED'
    b.emit('SUPABASE_MONITOR_RESULT', passed=passed, reason=reason)
    if not passed:
        b.notify(reason, observed)
    return 0 if passed else 1


if __name__ == '__main__':
    raise SystemExit(main())
