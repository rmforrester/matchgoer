"""Read-only Supabase exports. Only age ciphertext is persisted or uploaded.

Durable Auth data is distinct from session continuity. Volatile session/token
tables are intentionally empty in recovery; passwords are never logged.
"""
from contextlib import contextmanager
import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import io
import json
import os
from pathlib import Path
import re
import subprocess
import tarfile
import tempfile
import urllib.parse
import urllib.request
import uuid

try:
    from . import backup as b
except ImportError:
    import backup as b

PREFIX = 'supabase-recovery-v1/'
BUCKET = 'terraces-photos'
VOLATILE = {'sessions', 'refresh_tokens', 'one_time_tokens', 'flow_state',
            'mfa_challenges', 'mfa_amr_claims', 'saml_relay_states', 'sso_sessions',
            'oauth_authorizations', 'oauth_states', 'audit_log_entries'}
OBJECT = re.compile(r'^photos/[0-9a-f]{32}/(?:display|thumbnail)\.jpg$')


class RecoveryError(Exception):
    pass


def settings(env=os.environ):
    base = env.get('SUPABASE_URL', '').strip().rstrip('/')
    u = urllib.parse.urlsplit(base)
    if (u.scheme != 'https' or u.username or u.password or u.path or u.query or u.fragment
            or not re.fullmatch(r'[a-z0-9]+\.supabase\.co', u.hostname or '')):
        raise RecoveryError('SUPABASE_SOURCE_URL_INVALID')
    issuer = env.get('SUPABASE_JWT_ISSUER', '').strip()
    if issuer != base + '/auth/v1':
        raise RecoveryError('SUPABASE_SOURCE_ISSUER_NOT_CONFIRMED')
    return base, issuer, u.hostname.split('.')[0]


def pg_config(env=os.environ):
    _, _, ref = settings(env)
    raw = env.get('SUPABASE_BACKUP_DATABASE_URL', '').strip()
    if not raw:
        raise RecoveryError('SUPABASE_DATABASE_CREDENTIAL_MISSING')
    try:
        u = urllib.parse.urlsplit(raw)
        direct = u.hostname == 'db.' + ref + '.supabase.co'
        pooler = (u.hostname or '').endswith('.pooler.supabase.com') and urllib.parse.unquote(u.username or '').endswith('.' + ref)
        if u.scheme not in ('postgres', 'postgresql') or not (direct or pooler) or (u.port or 5432) != 5432:
            raise ValueError()
        e = b.pg_environment({**env, 'DATABASE_URL': raw})
        e.update(PGSSLMODE='verify-full', PGSSLROOTCERT='system', PGAPPNAME='matchgoer-supabase-recovery')
        return e
    except (ValueError, b.BackupError):
        raise RecoveryError('SUPABASE_DATABASE_SOURCE_NOT_CONFIRMED') from None


def database_shape(env=os.environ):
    """Return booleans only, never the URI, hostname, username or password."""
    raw = env.get('SUPABASE_BACKUP_DATABASE_URL', '')
    try:
        _, _, ref = settings(env)
        u = urllib.parse.urlsplit(raw.strip())
        return {'scheme_supported': u.scheme in ('postgres', 'postgresql'),
                'port_is_session_5432': (u.port or 5432) == 5432,
                'host_is_supabase_pooler': (u.hostname or '').endswith('.pooler.supabase.com'),
                'host_is_this_project_direct_database': u.hostname == 'db.' + ref + '.supabase.co',
                'pooler_user_matches_application_project': urllib.parse.unquote(u.username or '').endswith('.' + ref),
                'username_present': bool(u.username), 'password_present': bool(u.password),
                'database_path_present': bool(u.path.strip('/')), 'unexpected_fragment': bool(u.fragment),
                'surrounding_whitespace': raw != raw.strip()}
    except (ValueError, RecoveryError):
        return {'uri_or_project_configuration_unparseable': True}


def connect_pg(e):
    import psycopg
    return psycopg.connect(host=e['PGHOST'], port=e['PGPORT'], dbname=e['PGDATABASE'],
                           user=e['PGUSER'], password=e['PGPASSWORD'], sslmode=e['PGSSLMODE'],
                           sslrootcert=e.get('PGSSLROOTCERT'), connect_timeout=15, options=e['PGOPTIONS'])


def fingerprints(cur, schema, names):
    from psycopg import sql
    result = []
    for table in names:
        cur.execute(sql.SQL("SELECT count(*),md5(COALESCE(string_agg(h,'' ORDER BY h),'')) "
                            "FROM (SELECT md5(to_jsonb(t)::text) h FROM {}.{} t) q").format(
                                sql.Identifier(schema), sql.Identifier(table)))
        count, h = cur.fetchone()
        result.append({'schema': schema, 'table': table, 'rows': count, 'fingerprint': h})
    return result


@contextmanager
def auth_snapshot(e):
    with connect_pg(e) as conn:
        with conn.cursor() as cur:
            cur.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
            cur.execute("SELECT current_setting('transaction_read_only'),current_setting('server_version_num'),pg_export_snapshot()")
            readonly, version, snapshot = cur.fetchone()
            if readonly != 'on':
                raise RecoveryError('SUPABASE_READONLY_PROOF_FAILED')
            cur.execute("SELECT c.relname,has_table_privilege(current_user,c.oid,'SELECT') FROM pg_class c "
                        "JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='auth' AND c.relkind IN ('r','p') ORDER BY 1")
            tables = cur.fetchall()
            if not {'users', 'identities'}.issubset({t for t, _ in tables}) or not all(allowed for _, allowed in tables):
                raise RecoveryError('SUPABASE_COMPLETE_AUTH_SELECT_PERMISSION_MISSING')
            cur.execute("SELECT table_name,column_name FROM information_schema.columns WHERE table_schema='auth' AND table_name IN ('users','identities')")
            columns = set(cur.fetchall())
            required = {('users', 'id'), ('users', 'encrypted_password'), ('users', 'raw_app_meta_data'),
                        ('users', 'banned_until'), ('identities', 'user_id'), ('identities', 'provider')}
            if not required.issubset(columns):
                raise RecoveryError('SUPABASE_REQUIRED_AUTH_COLUMNS_MISSING')
            durable = [t for t, _ in tables if t not in VOLATILE]
            verification = {'version': 1, 'created_at_utc': b.now().isoformat(), 'server_version_num': version,
                            'tables': fingerprints(cur, 'auth', durable),
                            'intentionally_empty_session_tables': sorted(set(t for t, _ in tables) & VOLATILE),
                            'password_hashes_in_encrypted_archive': True, 'session_reauthentication_required': True}
            cur.execute("SELECT count(*),count(*) FILTER(WHERE COALESCE(encrypted_password,'')<>'') FROM auth.users")
            verification['auth_users'], verification['users_with_password_hashes'] = cur.fetchone()
            cur.execute('SELECT count(*) FROM auth.identities i LEFT JOIN auth.users u ON u.id=i.user_id WHERE u.id IS NULL')
            if cur.fetchone()[0]:
                raise RecoveryError('SUPABASE_ORPHAN_PROVIDER_IDENTITIES')
            try:
                yield snapshot, verification
            finally:
                conn.rollback()


def encrypt_json(value, path, recipient):
    p = subprocess.run(['age', '--encrypt', '--recipient', recipient, '--output', str(path)],
                       input=json.dumps(value, sort_keys=True, default=str).encode(),
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=90)
    if p.returncode:
        raise RecoveryError('SUPABASE_MANIFEST_ENCRYPTION_FAILED')


def export_auth(directory, recipient):
    e = pg_config()
    archive = directory / 'auth.dump.age'
    dump = age = None
    try:
        with auth_snapshot(e) as (snapshot, verification):
            args = ['pg_dump', '--format=custom', '--schema=auth', '--no-password',
                    '--lock-wait-timeout=10000', '--snapshot=' + snapshot]
            args += ['--exclude-table-data=auth.' + t for t in sorted(VOLATILE)]
            dump = subprocess.Popen(args, env=e, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
            age = subprocess.Popen(['age', '--encrypt', '--recipient', recipient, '--output', str(archive)],
                                   stdin=dump.stdout, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                   env={'PATH': os.environ['PATH']})
            dump.stdout.close()
            ac = age.wait(timeout=1500)
            dc = dump.wait(timeout=30)
            if ac or dc:
                raise RecoveryError('SUPABASE_AUTH_DUMP_OR_ENCRYPTION_FAILED')
        return archive, verification
    finally:
        for p in (age, dump):
            if p is not None and p.poll() is None:
                p.kill()
                p.wait(timeout=10)


class StorageReader:
    """Only bucket metadata, object listing and authenticated object GET exist."""
    def __init__(self, env=os.environ):
        self.base, _, _ = settings(env)
        key = env.get('SUPABASE_SECRET_KEY', '')
        if not key:
            raise RecoveryError('SUPABASE_STORAGE_CREDENTIAL_MISSING')
        self.headers = {'apikey': key, 'User-Agent': 'Matchgoer-Readonly-Recovery/1.0'}
        if not key.startswith('sb_secret_'):
            self.headers['Authorization'] = 'Bearer ' + key
        self.calls = 0

    def request(self, method, path, payload=None):
        allowed = (method == 'GET' and path == '/storage/v1/bucket/' + BUCKET) or (
            method == 'POST' and path == '/storage/v1/object/list/' + BUCKET) or (
            method == 'GET' and path.startswith('/storage/v1/object/' + BUCKET + '/photos/'))
        if not allowed or self.calls >= 200:
            raise RecoveryError('SUPABASE_STORAGE_READ_BOUND_EXCEEDED')
        self.calls += 1
        data = json.dumps(payload).encode() if payload is not None else None
        req = urllib.request.Request(self.base + path, data=data,
                                     headers={**self.headers, 'Content-Type': 'application/json'}, method=method)
        return urllib.request.urlopen(req, timeout=30)

    def inventory(self):
        with self.request('GET', '/storage/v1/bucket/' + BUCKET) as r:
            meta = json.load(r)
        if meta.get('id') != BUCKET or meta.get('public') is not False:
            raise RecoveryError('SUPABASE_PRIVATE_BUCKET_NOT_CONFIRMED')
        queue, objects = [''], {}
        while queue:
            prefix = queue.pop()
            offset = 0
            while True:
                with self.request('POST', '/storage/v1/object/list/' + BUCKET,
                                  {'prefix': prefix, 'limit': 100, 'offset': offset,
                                   'sortBy': {'column': 'name', 'order': 'asc'}}) as r:
                    rows = json.load(r)
                if not isinstance(rows, list):
                    raise RecoveryError('SUPABASE_STORAGE_INVENTORY_INVALID')
                for row in rows:
                    name = row.get('name', '')
                    if not name or '/' in name or name in ('.', '..'):
                        raise RecoveryError('SUPABASE_STORAGE_KEY_INVALID')
                    key = prefix + '/' + name if prefix else name
                    if row.get('id') is None and row.get('metadata') is None:
                        queue.append(key)
                    else:
                        if not OBJECT.fullmatch(key) or key in objects:
                            raise RecoveryError('SUPABASE_STORAGE_UNRECONCILED_OBJECT_IDENTITY')
                        objects[key] = row
                if len(rows) < 100:
                    break
                offset += 100
        return meta, objects

    def read(self, key):
        if not OBJECT.fullmatch(key):
            raise RecoveryError('SUPABASE_STORAGE_KEY_INVALID')
        with self.request('GET', '/storage/v1/object/' + BUCKET + '/' + key) as r:
            data = r.read(10_000_001)
        if not 0 < len(data) <= 10_000_000:
            raise RecoveryError('SUPABASE_PHOTO_SIZE_BOUND_EXCEEDED')
        return data


def railway_context():
    e = b.pg_environment()
    with connect_pg(e) as conn:
        with conn.cursor() as cur:
            cur.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
            cur.execute("SELECT i.issuer,i.subject,i.user_id,u.account_status FROM user_identities i JOIN users u ON u.user_id=i.user_id ORDER BY i.user_identity_id")
            identities = [{'issuer': a, 'subject': s, 'user_id': u, 'account_status': st} for a, s, u, st in cur.fetchall()]
            cur.execute("SELECT p.photo_id,p.owner_user_id,p.display_key,p.thumbnail_key,p.status,p.storage_deleted_at,p.removed_at,p.dispute_reason IS NOT NULL,EXISTS(SELECT 1 FROM terrace_photo_events e WHERE e.photo_id=p.photo_id AND e.event_type='STORAGE_READY' AND e.completed_at IS NOT NULL) FROM terrace_photos p ORDER BY p.photo_id")
            photos = [{'photo_id': a, 'owner_user_id': u, 'display_key': d, 'thumbnail_key': t, 'status': st,
                       'storage_deleted_at': deleted, 'removed_at': removed, 'held': held, 'storage_ready': ready}
                      for a, u, d, t, st, deleted, removed, held, ready in cur.fetchall()]
            cur.execute("SELECT payload FROM terrace_photo_events WHERE event_type='STORAGE_DELETE_REQUIRED'")
            cascades = [r[0] for r in cur.fetchall()]
            cur.execute("SELECT user_id FROM users WHERE account_status='deleted'")
            deleted_users = [r[0] for r in cur.fetchall()]
            conn.rollback()
    _, issuer, _ = settings()
    if any(i['issuer'] != issuer for i in identities):
        raise RecoveryError('SUPABASE_RAILWAY_ISSUER_CONFLICT')
    return {'identities': identities, 'photos': photos, 'cascade_deletions': cascades,
            'deleted_internal_users': deleted_users, 'captured_at_utc': b.now().isoformat()}


def export_photos(directory, recipient, context):
    reader = StorageReader()
    meta, objects = reader.inventory()
    suppressed, required = set(), set()
    for p in context['photos']:
        keys = {p['display_key'], p['thumbnail_key']}
        if p['status'] == 'REMOVED' or p['storage_deleted_at'] is not None:
            suppressed.update(keys)
        elif p['storage_ready']:
            required.update(keys)
    for item in context['cascade_deletions']:
        suppressed.update(k for k in (item.get('display_key'), item.get('thumbnail_key')) if k)
    if required - set(objects):
        raise RecoveryError('SUPABASE_REQUIRED_PHOTO_OBJECT_MISSING')
    if set(objects) - required - suppressed:
        raise RecoveryError('SUPABASE_ORPHAN_PHOTO_OBJECT_REQUIRES_RECONCILIATION')
    path = directory / 'photos.tar.age'
    age = subprocess.Popen(['age', '--encrypt', '--recipient', recipient, '--output', str(path)],
                           stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                           env={'PATH': os.environ['PATH']})
    manifest = {'version': 1, 'bucket': meta, 'objects': [], 'railway_context': context,
                'source_issuer': settings()[1], 'created_at_utc': b.now().isoformat()}
    try:
        with tarfile.open(fileobj=age.stdin, mode='w|') as tar:
            for key in sorted(required):
                data = reader.read(key)
                recorded_size = objects[key].get('metadata', {}).get('size')
                if recorded_size is not None and int(recorded_size) != len(data):
                    raise RecoveryError('SUPABASE_PHOTO_SIZE_METADATA_MISMATCH')
                info = tarfile.TarInfo('objects/' + key)
                info.size = len(data)
                tar.addfile(info, io.BytesIO(data))
                manifest['objects'].append({'key': key, 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest(),
                                            'storage_metadata': objects[key]})
            raw = json.dumps(manifest, sort_keys=True, default=str).encode()
            info = tarfile.TarInfo('manifest.json'); info.size = len(raw)
            tar.addfile(info, io.BytesIO(raw))
        age.stdin.close()
        if age.wait(timeout=120):
            raise RecoveryError('SUPABASE_PHOTO_ENCRYPTION_FAILED')
    finally:
        if age.poll() is None:
            age.kill(); age.wait(timeout=10)
    return path, {'objects': len(manifest['objects']), 'source_bytes': sum(x['bytes'] for x in manifest['objects']),
                  'private_bucket_verified': True, 'read_only_storage_requests': reader.calls}, manifest


def upload_file(s3, bucket, file, key):
    h, size = b.digest(file), file.stat().st_size
    b.put_ciphertext(s3, bucket, key, file, h, size)
    b.verify_object(s3, bucket, key, h, size)
    return {'key': key, 'sha256': h, 'bytes': size}


def export_point():
    c = b.config()
    s3, bucket = b.client(c), c['BACKUP_R2_BUCKET']
    observed = b.now()
    prefix = PREFIX + 'points/' + observed.strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex[:8] + '/'
    result = {'version': 1, 'kind': 'supabase-independent-recovery', 'completed_at_utc': None,
              'stages': {}, 'artifacts': [], 'deletion_protection': 'CHECKPOINT_ONLY_NOT_RELEASE_ACCEPTED',
              'complete_recovery': False}
    with tempfile.TemporaryDirectory(prefix='matchgoer-supabase-ciphertext-') as td:
        directory = Path(td); os.chmod(directory, 0o700)
        try:
            archive, verification = export_auth(directory, c['BACKUP_AGE_RECIPIENT'])
            verification.update(source_issuer=settings()[1])
            v = directory / 'auth-verification.json.age'
            encrypt_json(verification, v, c['BACKUP_AGE_RECIPIENT'])
            result['artifacts'] += [upload_file(s3, bucket, archive, prefix + archive.name), upload_file(s3, bucket, v, prefix + v.name)]
            result['stages']['auth'] = {'passed': True, 'auth_users': verification['auth_users'],
                                        'durable_tables': len(verification['tables']), 'session_reauthentication_required': True}
        except Exception as exc:
            result['stages']['auth'] = {'passed': False, 'reason': safe_reason(exc)}
            b.notify('SUPABASE_AUTH_' + safe_reason(exc), observed)
        try:
            context = railway_context()
            photos, summary, _ = export_photos(directory, c['BACKUP_AGE_RECIPIENT'], context)
            result['artifacts'].append(upload_file(s3, bucket, photos, prefix + photos.name))
            result['stages']['photos'] = {'passed': True, **summary}
        except Exception as exc:
            result['stages']['photos'] = {'passed': False, 'reason': safe_reason(exc)}
            b.notify('SUPABASE_PHOTOS_' + safe_reason(exc), observed)
        result['data_exports_complete'] = all(x['passed'] for x in result['stages'].values())
        result['completed_at_utc'] = b.now().isoformat()
        s3.put_object(Bucket=bucket, Key=prefix + 'receipt.json', Body=json.dumps(result, sort_keys=True).encode(),
                      ContentType='application/json', StorageClass='STANDARD', IfNoneMatch='*')
    b.emit('SUPABASE_RECOVERY_RESULT', **result)
    return result


def safe_reason(exc):
    if isinstance(exc, (RecoveryError, b.BackupError)):
        return str(exc)
    state = getattr(exc, 'sqlstate', None)
    if isinstance(state, str) and re.fullmatch(r'[A-Z0-9]{5}', state):
        return 'DATABASE_SQLSTATE_' + state
    if isinstance(exc, urllib.error.HTTPError):
        return 'STORAGE_HTTP_' + str(exc.code)
    return 'RECOVERY_OPERATION_FAILED'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--probe', action='store_true', help='SELECT-only access/coverage and storage metadata probe; no export/upload')
    args = parser.parse_args()
    try:
        if args.probe:
            outcomes = {}
            try:
                e = pg_config()
                with auth_snapshot(e) as (_, verification):
                    outcomes['auth'] = {'passed': True, 'complete_durable_table_select_access': True,
                                        'auth_users': verification['auth_users'], 'durable_tables': len(verification['tables']),
                                        'password_hash_rows_accessible': verification['users_with_password_hashes'],
                                        'session_tables_excluded': verification['intentionally_empty_session_tables']}
                context = railway_context()
                with connect_pg(e) as conn:
                    with conn.cursor() as cur:
                        cur.execute('SELECT count(*) FROM auth.users WHERE id=ANY(%s::uuid[])',
                                    ([i['subject'] for i in context['identities']],))
                        linked = cur.fetchone()[0]
                    conn.rollback()
                if linked != len({i['subject'] for i in context['identities']}):
                    raise RecoveryError('SUPABASE_RAILWAY_SUBJECT_MISMATCH')
                outcomes['auth']['railway_subjects_matched'] = linked
            except Exception as exc:
                outcomes['auth'] = {'passed': False, 'reason': safe_reason(exc), 'safe_database_shape': database_shape()}
            try:
                reader = StorageReader()
                meta, objects = reader.inventory()
                outcomes['photos'] = {'passed': True, 'private_bucket': meta['public'] is False,
                                      'storage_objects': len(objects),
                                      'storage_bytes': sum(int(o.get('metadata', {}).get('size', 0)) for o in objects.values()),
                                      'read_only_storage_requests': reader.calls}
            except Exception as exc:
                outcomes['photos'] = {'passed': False, 'reason': safe_reason(exc)}
            passed = all(v['passed'] for v in outcomes.values())
            b.emit('SUPABASE_ACCESS_PROBE', passed=passed, stages=outcomes, data_exported=False,
                   data_uploaded=False, secret_values_printed=False)
            return 0 if passed else 1
        r = export_point()
        return 0 if r['data_exports_complete'] else 1
    except Exception as exc:
        reason = safe_reason(exc)
        b.emit('SUPABASE_RECOVERY_FAILED', reason=reason)
        b.notify('SUPABASE_' + reason, b.now())
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
