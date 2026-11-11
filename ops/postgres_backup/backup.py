"""PostgreSQL -> age -> private R2. No plaintext archives or row values in logs."""
import argparse
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import tempfile
import time
import urllib.parse
import urllib.request
import uuid

PREFIX = 'railway-postgres-v1/'
SOURCE = '38e29e99-af66-49d7-afe1-5c8c4a99ca83/f38d1bc9-55ad-46ca-bc33-4fe27786a124/f4a3e7e3-d6fc-4989-b847-20c4ed162c49'
RECEIPT = re.compile(r'^railway-postgres-v1/(daily/[0-9]{8}T[0-9]{6}Z-[a-f0-9]{8}|monthly/[0-9]{4}-[0-9]{2})/receipt\.json$')


class BackupError(Exception):
    """Only fixed error codes may cross the process/log boundary."""


def now():
    return datetime.now(timezone.utc)


def emit(code, **safe):
    print(json.dumps({'event': code, **safe}), flush=True)


def digest(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for part in iter(lambda: f.read(1024 * 1024), b''):
            h.update(part)
    return h.hexdigest()


def config(env=os.environ, require_recipient=True):
    needed = ['BACKUP_R2_ENDPOINT', 'BACKUP_R2_BUCKET', 'BACKUP_R2_ACCESS_KEY_ID',
              'BACKUP_R2_SECRET_ACCESS_KEY']
    if require_recipient:
        needed.append('BACKUP_AGE_RECIPIENT')
    if any(not env.get(k) for k in needed):
        raise BackupError('BACKUP_CONFIGURATION_INCOMPLETE')
    endpoint = urllib.parse.urlsplit(env['BACKUP_R2_ENDPOINT'])
    if (endpoint.scheme != 'https' or endpoint.username or endpoint.password or endpoint.query
            or endpoint.fragment or endpoint.path not in ('', '/') or
            not re.fullmatch(r'[a-f0-9]{32}(?:\.(?:eu|us))?\.r2\.cloudflarestorage\.com', endpoint.hostname or '')):
        raise BackupError('BACKUP_ENDPOINT_INVALID')
    if require_recipient and not re.fullmatch(r'age1[0-9a-z]{58}', env['BACKUP_AGE_RECIPIENT']):
        raise BackupError('BACKUP_PUBLIC_RECIPIENT_INVALID')
    if env['BACKUP_R2_BUCKET'] != 'matchgoer-postgres-backups':
        raise BackupError('BACKUP_BUCKET_NOT_APPROVED')
    return {k: env[k] for k in needed}


def client(c):
    import boto3
    from botocore.config import Config
    return boto3.client('s3', endpoint_url=c['BACKUP_R2_ENDPOINT'], region_name='auto',
                        aws_access_key_id=c['BACKUP_R2_ACCESS_KEY_ID'],
                        aws_secret_access_key=c['BACKUP_R2_SECRET_ACCESS_KEY'],
                        config=Config(connect_timeout=10, read_timeout=60,
                                      request_checksum_calculation='when_required',
                                      response_checksum_validation='when_required',
                                      retries={'max_attempts': 3, 'mode': 'standard'}))


def pg_environment(env=os.environ):
    """Credentials are environment-only; never included in process arguments."""
    try:
        u = urllib.parse.urlsplit(env['DATABASE_URL'])
        if u.scheme not in ('postgres', 'postgresql') or not u.hostname or not u.path.strip('/'):
            raise ValueError()
        # Prevent inherited libpq settings and URI options overriding safety settings.
        result = {k: v for k, v in env.items() if k in ('PATH', 'LANG', 'LC_ALL', 'TMPDIR', 'HOME', 'SYSTEMROOT')}
        result.update(PGHOST=u.hostname, PGPORT=str(u.port or 5432),
                      PGDATABASE=urllib.parse.unquote(u.path[1:]),
                      PGUSER=urllib.parse.unquote(u.username or ''),
                      PGPASSWORD=urllib.parse.unquote(u.password or ''),
                      PGSSLMODE='require', PGCONNECT_TIMEOUT='15',
                      PGAPPNAME='matchgoer-independent-backup',
                      PGOPTIONS='-c default_transaction_read_only=on -c statement_timeout=1200000 -c lock_timeout=10000')
        if not result['PGUSER'] or not result['PGPASSWORD']:
            raise ValueError()
        return result
    except (ValueError, KeyError):
        raise BackupError('BACKUP_DATABASE_CONFIGURATION_INVALID') from None


@contextmanager
def database_snapshot(pg_env):
    import psycopg
    from psycopg import sql
    args = {k: pg_env[v] for k, v in {'host': 'PGHOST', 'port': 'PGPORT', 'dbname': 'PGDATABASE',
            'user': 'PGUSER', 'password': 'PGPASSWORD', 'sslmode': 'PGSSLMODE',
            'connect_timeout': 'PGCONNECT_TIMEOUT', 'options': 'PGOPTIONS'}.items()}
    with psycopg.connect(**args) as conn:
        with conn.cursor() as cur:
            cur.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
            cur.execute('SELECT pg_export_snapshot(),current_setting(\'server_version_num\')')
            snapshot, version = cur.fetchone()
            cur.execute("SELECT n.nspname,c.relname FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
                        "WHERE c.relkind IN ('r','p') AND n.nspname NOT IN ('information_schema') "
                        "AND n.nspname !~ '^pg_' ORDER BY 1,2")
            relations = cur.fetchall()
            fingerprints = []
            for schema, table in relations:
                cur.execute(sql.SQL("SELECT count(*),md5(COALESCE(string_agg(h,'' ORDER BY h),'')) "
                                    "FROM (SELECT md5(to_jsonb(t)::text) h FROM {}.{} t) q").format(
                                        sql.Identifier(schema), sql.Identifier(table)))
                count, fingerprint = cur.fetchone()
                fingerprints.append({'schema': schema, 'table': table, 'rows': count, 'fingerprint': fingerprint})
            if not {'fixtures', 'teams', 'venues'}.issubset({t for s, t in relations if s == 'public'}):
                raise BackupError('BACKUP_SOURCE_SCHEMA_NOT_MATCHGOER')
            try:
                yield snapshot, {'version': 1, 'source': SOURCE, 'server_version_num': version,
                                 'tables': fingerprints, 'snapshot_consistency': 'exported-repeatable-read'}
            finally:
                conn.rollback()


def make_archive(destination, recipient, env=os.environ):
    """Stream pg_dump straight to age. Only ciphertext touches ephemeral disk."""
    pg_env = pg_environment(env)
    dump = encryption = None
    started = time.monotonic()
    try:
        with database_snapshot(pg_env) as (snapshot, verification):
            dump = subprocess.Popen(['pg_dump', '--format=custom', '--no-password',
                                     '--lock-wait-timeout=10000', '--snapshot=' + snapshot], env=pg_env,
                                    stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
            encryption = subprocess.Popen(['age', '--encrypt', '--recipient', recipient,
                                           '--output', str(destination)], stdin=dump.stdout,
                                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                          env={'PATH': os.environ['PATH']})
            dump.stdout.close()
            remaining = lambda: max(1, 1500 - (time.monotonic() - started))
            encrypt_code = encryption.wait(timeout=remaining())
            dump_code = dump.wait(timeout=remaining())
        if dump_code or encrypt_code or not destination.is_file() or destination.stat().st_size < 100:
            raise BackupError('BACKUP_DUMP_OR_ENCRYPTION_FAILED')
        with destination.open('rb') as f:
            if not f.read(64).startswith(b'age-encryption.org/v1\n'):
                raise BackupError('BACKUP_CIPHERTEXT_HEADER_INVALID')
        verification_path = destination.with_name('verification.json.age')
        p = subprocess.run(['age', '--encrypt', '--recipient', recipient, '--output', str(verification_path)],
                           input=json.dumps(verification, sort_keys=True).encode(),
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=45,
                           env={'PATH': os.environ['PATH']})
        if p.returncode:
            raise BackupError('BACKUP_VERIFICATION_ENCRYPTION_FAILED')
        return verification_path
    except (OSError, subprocess.TimeoutExpired):
        raise BackupError('BACKUP_DUMP_OR_ENCRYPTION_UNAVAILABLE') from None
    finally:
        for p in (encryption, dump):
            if p is not None and p.poll() is None:
                p.kill()
                p.wait(timeout=10)


def not_found(exc):
    return getattr(exc, 'response', {}).get('Error', {}).get('Code') in ('404', 'NoSuchKey', 'NotFound')


def read_receipt(s3, bucket, key):
    if not RECEIPT.fullmatch(key):
        raise BackupError('BACKUP_RECEIPT_KEY_INVALID')
    body = s3.get_object(Bucket=bucket, Key=key)['Body']
    try:
        data = body.read(16385)
    finally:
        body.close()
    if len(data) > 16384:
        raise BackupError('BACKUP_RECEIPT_OVERSIZED')
    r = json.loads(data)
    prefix = key[:-len('receipt.json')]
    if (r.get('version') != 1 or r.get('source') != SOURCE or
            r.get('object_key') != prefix + 'database.dump.age' or
            r.get('verified') is not True or not re.fullmatch(r'[a-f0-9]{64}', r.get('sha256', '')) or
            type(r.get('bytes')) is not int or r['bytes'] < 100 or
            r.get('verification_key') != prefix + 'verification.json.age' or
            not re.fullmatch(r'[a-f0-9]{64}', r.get('verification_sha256', '')) or
            type(r.get('verification_bytes')) is not int or r['verification_bytes'] < 100):
        raise BackupError('BACKUP_RECEIPT_INVALID')
    stamp = datetime.fromisoformat(r['completed_at_utc'])
    if stamp.tzinfo is None or stamp > now() + timedelta(minutes=5):
        raise BackupError('BACKUP_RECEIPT_TIME_INVALID')
    return r


def receipts(s3, bucket):
    rows = []
    pages = s3.get_paginator('list_objects_v2').paginate(Bucket=bucket, Prefix=PREFIX)
    for page in pages:
        for obj in page.get('Contents', []):
            if RECEIPT.fullmatch(obj['Key']):
                r = read_receipt(s3, bucket, obj['Key'])
                rows.append((obj['Key'], r))
    return sorted(rows, key=lambda x: x[1]['completed_at_utc'], reverse=True)


def verify_object(s3, bucket, key, expected_hash, expected_size, content=True):
    # A multipart ETag is not a SHA-256 checksum. Read ciphertext back independently.
    head = s3.head_object(Bucket=bucket, Key=key)
    if head['ContentLength'] != expected_size or head.get('Metadata', {}).get('sha256') != expected_hash:
        raise BackupError('BACKUP_OBJECT_METADATA_MISMATCH')
    if not content:
        return
    response = s3.get_object(Bucket=bucket, Key=key)
    stream = response['Body']
    h = hashlib.sha256()
    size = 0
    try:
        while True:
            part = stream.read(1024 * 1024)
            if not part:
                break
            h.update(part)
            size += len(part)
    finally:
        stream.close()
    if size != expected_size or h.hexdigest() != expected_hash:
        raise BackupError('BACKUP_OBJECT_CHECKSUM_MISMATCH')


def publish(s3, bucket, archive, verification, prefix, completed, recipient):
    key = prefix + 'database.dump.age'
    h, size = digest(archive), archive.stat().st_size
    # Never replace a successful recovery point.
    put_ciphertext(s3, bucket, key, archive, h, size)
    verify_object(s3, bucket, key, h, size)
    verification_key = prefix + 'verification.json.age'
    vh, vs = digest(verification), verification.stat().st_size
    put_ciphertext(s3, bucket, verification_key, verification, vh, vs)
    verify_object(s3, bucket, verification_key, vh, vs)
    r = {'version': 1, 'source': SOURCE, 'object_key': key, 'sha256': h, 'bytes': size,
         'completed_at_utc': completed.isoformat(), 'verified': True,
         'encryption': 'age-X25519', 'public_recipient_sha256': hashlib.sha256(recipient.encode()).hexdigest()}
    r.update(verification_key=verification_key, verification_sha256=vh, verification_bytes=vs)
    # A success receipt is created only after full ciphertext read-back verification.
    s3.put_object(Bucket=bucket, Key=prefix + 'receipt.json',
                  Body=json.dumps(r, sort_keys=True).encode(), ContentType='application/json',
                  StorageClass='STANDARD', IfNoneMatch='*')
    saved = read_receipt(s3, bucket, prefix + 'receipt.json')
    if saved != r:
        raise BackupError('BACKUP_RECEIPT_READBACK_MISMATCH')
    return r


def put_ciphertext(s3, bucket, key, file, h, size):
    try:
        s3.head_object(Bucket=bucket, Key=key)
    except Exception as exc:
        if not not_found(exc):
            raise
        with file.open('rb') as f:
            s3.put_object(Bucket=bucket, Key=key, Body=f, ContentType='application/octet-stream',
                          StorageClass='STANDARD', Metadata={'sha256': h}, IfNoneMatch='*')
    else:
        # Retry a partially completed upload only when the existing ciphertext matches exactly.
        verify_object(s3, bucket, key, h, size)


def retention_candidates(rows):
    """Keep 30 successful UTC dates and 3 successful calendar months; never broad sync."""
    daily, monthly, remove = set(), set(), []
    for key, r in sorted(rows, key=lambda x: x[1]['completed_at_utc'], reverse=True):
        if not RECEIPT.fullmatch(key):
            raise BackupError('BACKUP_RETENTION_KEY_INVALID')
        day = datetime.fromisoformat(r['completed_at_utc']).date().isoformat()
        if '/daily/' in key:
            if day in daily or len(daily) >= 30:
                remove.append((key, r))
            else:
                daily.add(day)
        else:
            month = key.split('/')[-2]
            if month in monthly or len(monthly) >= 3:
                remove.append((key, r))
            else:
                monthly.add(month)
    return remove


def prune(s3, bucket, rows):
    removed, protected = 0, 0
    for key, r in retention_candidates(rows):
        try:
            # Bucket locks enforce a minimum age; fail-safe retention may temporarily exceed counts.
            # Remove the success marker first. An interrupted prune can leave extra
            # ciphertext, but cannot advertise a recovery point whose files are gone.
            s3.delete_object(Bucket=bucket, Key=key)
            s3.delete_object(Bucket=bucket, Key=r['verification_key'])
            s3.delete_object(Bucket=bucket, Key=r['object_key'])
            removed += 1
        except Exception as exc:
            if getattr(exc, 'response', {}).get('Error', {}).get('Code') in ('AccessDenied', 'ObjectLockedByBucketPolicy'):
                protected += 1
            else:
                raise BackupError('BACKUP_RETENTION_FAILED') from None
    return {'removed_recovery_points': removed, 'locked_or_permission_deferred': protected}


def health(s3, bucket, rows, observed, content=True, expected_today=False):
    daily = [(k, r) for k, r in rows if '/daily/' in k]
    if not daily:
        return False, 'BACKUP_NO_VERIFIED_RECOVERY_POINT'
    r = max(daily, key=lambda x: x[1]['completed_at_utc'])[1]
    age = observed - datetime.fromisoformat(r['completed_at_utc'])
    if age > timedelta(hours=30):
        return False, 'BACKUP_STALE_OVER_30_HOURS'
    if expected_today and (observed.hour, observed.minute) >= (9, 10) and datetime.fromisoformat(r['completed_at_utc']).date() < observed.date():
        return False, 'BACKUP_EXPECTED_DAILY_POINT_MISSING'
    verify_object(s3, bucket, r['object_key'], r['sha256'], r['bytes'], content=content)
    verify_object(s3, bucket, r['verification_key'], r['verification_sha256'], r['verification_bytes'], content=content)
    return True, 'BACKUP_FRESH'


def record_attempt(state, observed, reason=None):
    c = config()
    body = {'version': 1, 'state': state, 'at_utc': observed.isoformat(), 'reason': reason}
    client(c).put_object(Bucket=c['BACKUP_R2_BUCKET'], Key=PREFIX + 'status/latest-attempt.json',
                         Body=json.dumps(body).encode(), ContentType='application/json', StorageClass='STANDARD')


def attempt_health(s3, bucket, observed):
    try:
        stream = s3.get_object(Bucket=bucket, Key=PREFIX + 'status/latest-attempt.json')['Body']
    except Exception as exc:
        if not_found(exc):
            return True, 'BACKUP_NO_ATTEMPT_METADATA'
        raise
    try:
        raw = stream.read(4097)
    finally:
        stream.close()
    if len(raw) > 4096:
        return False, 'BACKUP_ATTEMPT_METADATA_INVALID'
    r = json.loads(raw)
    stamp = datetime.fromisoformat(r['at_utc'])
    if r.get('version') != 1 or stamp.tzinfo is None or stamp > observed + timedelta(minutes=5):
        return False, 'BACKUP_ATTEMPT_METADATA_INVALID'
    if r.get('state') in ('FAILED', 'WARNING'):
        return False, 'BACKUP_LATEST_ATTEMPT_FAILED_OR_WARNING'
    if r.get('state') == 'RUNNING' and observed - stamp > timedelta(hours=2):
        return False, 'BACKUP_LATEST_ATTEMPT_STUCK'
    if r.get('state') not in ('RUNNING', 'SUCCESS'):
        return False, 'BACKUP_ATTEMPT_METADATA_INVALID'
    return True, 'BACKUP_ATTEMPT_HEALTHY'


def alert(reason, observed, test=False, env=os.environ):
    key = env.get('FIXTURE_INTEGRITY_RESEND_API_KEY', '')
    sender = 'accounts@mail.matchgoer.com'
    recipient = env.get('BACKUP_ALERT_TO', '')
    if not re.fullmatch(r'[^\s@,;<>]+@[^\s@,;<>]+\.[^\s@,;<>]+', recipient):
        raise BackupError('BACKUP_ALERT_RECIPIENT_INVALID')
    if not key:
        raise BackupError('BACKUP_ALERT_CREDENTIAL_UNAVAILABLE')
    title = 'Matchgoer database backup — ' + ('safe test alert' if test else 'attention required')
    body = {'from': sender, 'to': [recipient], 'subject': title,
            'text': ('Safe backup alert delivery test. No production restore or fixture processing occurred.' if test else
                     'Backup protection requires attention. Code: ' + reason + '\nObserved UTC: ' + observed.isoformat() +
                     '\nUnrelated Matchgoer services continue. This message contains no database records or credentials.')}
    request = urllib.request.Request('https://api.resend.com/emails', data=json.dumps(body).encode(),
                                    headers={'Authorization': 'Bearer ' + key, 'Content-Type': 'application/json',
                                             'User-Agent': 'Matchgoer-DatabaseBackup/1.0',
                                             'Idempotency-Key': 'database-backup-' + observed.date().isoformat() + '-' + reason},
                                    method='POST')
    try:
        with urllib.request.urlopen(request, timeout=25) as response:
            result = json.load(response)
        if not result.get('id'):
            raise ValueError()
    except Exception:
        raise BackupError('BACKUP_ALERT_DELIVERY_FAILED') from None
    return {'accepted': True, 'email_id': result['id'], 'inbox_delivery_confirmed': False}


def notify(reason, observed):
    try:
        emit('BACKUP_ALERT', reason=reason, **alert(reason, observed))
    except Exception:
        # Email transport must never prevent an otherwise safe backup.
        emit('BACKUP_ALERT_UNAVAILABLE', reason=reason)


def run(observed, check_only=False):
    c = config(require_recipient=not check_only)
    s3, bucket = client(c), c['BACKUP_R2_BUCKET']
    try:
        rows = receipts(s3, bucket)
    except (BackupError, ValueError):
        if check_only:
            raise
        notify('BACKUP_OLDER_RECEIPT_INVALID', observed)
        rows = []
    if check_only:
        ok, reason = health(s3, bucket, rows, observed, content=False, expected_today=True)
        if ok:
            ok, reason = attempt_health(s3, bucket, observed)
        if not ok:
            notify(reason, observed)
        return {'passed': ok, 'reason': reason, 'database_connected': False}
    latest = [r for k, r in rows if '/daily/' in k]
    if latest:
        try:
            ok, reason = health(s3, bucket, rows, observed)
            if not ok:
                notify(reason, observed)
        except BackupError:
            notify('BACKUP_OLDER_CIPHERTEXT_INVALID', observed)
            latest = []
    existing = next((r for r in latest if datetime.fromisoformat(r['completed_at_utc']).date() == observed.date()), None)
    with tempfile.TemporaryDirectory(prefix='matchgoer-encrypted-backup-') as td:
        os.chmod(td, 0o700)
        archive = Path(td) / 'database.dump.age'
        if existing:
            verify_object(s3, bucket, existing['object_key'], existing['sha256'], existing['bytes'])
            verify_object(s3, bucket, existing['verification_key'], existing['verification_sha256'], existing['verification_bytes'])
            s3.download_file(bucket, existing['object_key'], str(archive))
            verification = Path(td) / 'verification.json.age'
            s3.download_file(bucket, existing['verification_key'], str(verification))
            if digest(archive) != existing['sha256'] or digest(verification) != existing['verification_sha256']:
                raise BackupError('BACKUP_RETRY_DOWNLOAD_CHECKSUM_MISMATCH')
            daily = existing
            completed = datetime.fromisoformat(existing['completed_at_utc'])
        else:
            verification = make_archive(archive, c['BACKUP_AGE_RECIPIENT'])
            stamp = observed.strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex[:8]
            completed = now()
            daily = publish(s3, bucket, archive, verification, PREFIX + 'daily/' + stamp + '/', completed, c['BACKUP_AGE_RECIPIENT'])
        month_key = PREFIX + 'monthly/' + observed.strftime('%Y-%m') + '/receipt.json'
        warnings = []
        if not any(k == month_key for k, _ in rows):
            try:
                publish(s3, bucket, archive, verification, month_key[:-len('receipt.json')], completed, c['BACKUP_AGE_RECIPIENT'])
            except Exception:
                warnings.append('BACKUP_MONTHLY_POINT_INCOMPLETE')
                notify(warnings[-1], observed)
        try:
            retained = prune(s3, bucket, receipts(s3, bucket))
        except Exception:
            warnings.append('BACKUP_RETENTION_INCOMPLETE')
            notify(warnings[-1], observed)
            retained = {}
    return {'passed': True, 'object_key': daily['object_key'], 'sha256': daily['sha256'],
            'encrypted_bytes': daily['bytes'], 'completed_at_utc': daily['completed_at_utc'],
            'already_backed_up_today': existing is not None, 'warnings': warnings, **retained}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--check', action='store_true', help='Independent stale/ciphertext checker; no DB connection')
    parser.add_argument('--test-alert', action='store_true')
    parser.add_argument('--preflight', action='store_true', help='Validate recipient and R2 access without a DB connection/upload')
    parser.add_argument('--test-stale-alert', action='store_true', help='Read-only simulated stale health check and clearly labelled test email')
    args = parser.parse_args()
    observed, start = now(), time.monotonic()
    if hasattr(signal, 'SIGALRM'):
        def timeout(*_):
            raise BackupError('BACKUP_WALL_CLOCK_TIMEOUT')
        signal.signal(signal.SIGALRM, timeout)
        signal.alarm(2700)
    try:
        if args.test_alert:
            emit('BACKUP_TEST_ALERT', **alert('SAFE_TEST', observed, test=True))
            return 0
        if args.test_stale_alert:
            c = config(require_recipient=False)
            s3 = client(c)
            rows = receipts(s3, c['BACKUP_R2_BUCKET'])
            ok, reason = health(s3, c['BACKUP_R2_BUCKET'], rows, observed + timedelta(hours=31), content=False)
            if ok:
                raise BackupError('BACKUP_STALE_SIMULATION_NOT_TRIGGERED')
            emit('BACKUP_STALE_SIMULATION', reason=reason, production_objects_modified=False,
                 **alert('SAFE_TEST_STALE', observed, test=True))
            return 0
        if args.preflight:
            c = config()
            p = subprocess.run(['age', '--encrypt', '--recipient', c['BACKUP_AGE_RECIPIENT']],
                               input=b'Matchgoer public recipient validation only',
                               capture_output=True, timeout=30)
            if p.returncode or not p.stdout.startswith(b'age-encryption.org/v1\n'):
                raise BackupError('BACKUP_PUBLIC_RECIPIENT_INVALID')
            s3 = client(c)
            s3.list_objects_v2(Bucket=c['BACKUP_R2_BUCKET'], Prefix=PREFIX, MaxKeys=1)
            emit('BACKUP_PREFLIGHT_PASS', bucket=c['BACKUP_R2_BUCKET'],
                 public_recipient_sha256=hashlib.sha256(c['BACKUP_AGE_RECIPIENT'].encode()).hexdigest(),
                 database_connected=False, uploaded=False)
            return 0
        if not args.check:
            record_attempt('RUNNING', observed)
        result = run(observed, args.check)
        if not args.check:
            try:
                record_attempt('WARNING' if result.get('warnings') else 'SUCCESS', now())
            except Exception:
                notify('BACKUP_ATTEMPT_STATUS_WRITE_FAILED', observed)
        emit('BACKUP_RESULT', elapsed_seconds=round(time.monotonic() - start, 2), **result)
        return 0 if result['passed'] else 1
    except Exception as exc:
        reason = str(exc) if isinstance(exc, BackupError) else 'BACKUP_OPERATION_FAILED'
        provider_code = getattr(exc, 'response', {}).get('Error', {}).get('Code')
        if provider_code in ('AccessDenied', 'SignatureDoesNotMatch', 'InvalidAccessKeyId', 'NoSuchBucket', 'ObjectLockedByBucketPolicy', 'PreconditionFailed'):
            reason = 'BACKUP_R2_' + provider_code
        sqlstate = getattr(exc, 'sqlstate', None)
        if isinstance(sqlstate, str) and re.fullmatch(r'[0-9A-Z]{5}', sqlstate):
            reason = 'BACKUP_DATABASE_SQLSTATE_' + sqlstate
        emit('BACKUP_FAILED', reason=reason)
        if not args.check and not args.test_alert and not args.test_stale_alert and not args.preflight:
            try:
                record_attempt('FAILED', now(), reason)
            except Exception:
                pass
        notify(reason, observed)
        return 1
    finally:
        if hasattr(signal, 'SIGALRM'):
            signal.alarm(0)


if __name__ == '__main__':
    raise SystemExit(main())
