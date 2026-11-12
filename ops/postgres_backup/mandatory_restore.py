"""Offline combined recovery. No network clients, production URLs or bypass mode.

The operator-pinned inventory is an independent incident evidence freeze, not a
backup's self-certification. Its provenance/capture attestations require human
verification; hashes and contiguous segment checks cannot prove uncaptured acts.
All plaintext must be in disposable RAM-backed storage. Never expose a staging
target, including after failure. A PASS applies only through the fixed cutoff.
"""
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import tarfile
import time
from datetime import datetime, timedelta, timezone

import psycopg
from psycopg import sql

import backup as b
from deletion_suppression import validate_event
from recovery_policy import timestamp, MAX_POINT_DAYS


def require(ok, code):
    if not ok:
        raise b.BackupError(code)


def local_file(root, name):
    require(isinstance(name, str), 'RESTORE_PATH_INVALID')
    path = (root / name).resolve()
    require(path.is_relative_to(root.resolve()) and path.is_file(), 'RESTORE_ARTIFACT_MISSING_OR_UNSAFE')
    return path


def checked(root, item):
    path = local_file(root, item['file'])
    require(path.stat().st_size == item['bytes'] and b.digest(path) == item['sha256'],
            'RESTORE_ARTIFACT_CHECKSUM_MISMATCH')
    return path


def decrypt(path, identity, limit=32 * 1024 * 1024):
    # Only age sees the identity file; no secret text or raw tool output escapes.
    result = subprocess.run(['age', '--decrypt', '--identity', str(identity), str(path)],
                            capture_output=True, timeout=180)
    require(result.returncode == 0 and len(result.stdout) <= limit, 'RESTORE_DECRYPTION_OR_SIZE_FAILED')
    return result.stdout


def load_plan(archive, verification, receipt_path):
    """No key or target access until the inventory and all ciphertext validate."""
    filename = os.environ.get('RESTORE_RECOVERY_BUNDLE_FILE')
    pin = os.environ.get('RESTORE_RECOVERY_BUNDLE_SHA256')
    require(filename and pin, 'RESTORE_MANDATORY_BUNDLE_REQUIRED')
    path = Path(filename)
    require(b.digest(path) == pin, 'RESTORE_INVENTORY_PIN_MISMATCH')
    plan = json.loads(path.read_text())
    require(plan.get('version') == 1, 'RESTORE_INVENTORY_VERSION_INVALID')
    require(plan.get('source') == b.SOURCE, 'RESTORE_SOURCE_MISMATCH')
    require(plan.get('isolated_staging') is True, 'RESTORE_ISOLATION_REQUIRED')
    require(not any(os.environ.get(k) for k in ('RAILWAY_ENVIRONMENT_ID', 'SUPABASE_SECRET_KEY',
                                               'SUPABASE_BACKUP_DATABASE_URL', 'DATABASE_URL')),
            'RESTORE_PRODUCTION_CONFIGURATION_REFUSED')
    now = datetime.now(timezone.utc)
    cutoff = timestamp(plan['cutoff_utc'])
    require(now - timedelta(hours=24) <= cutoff <= now, 'RESTORE_CUTOFF_INVALID_OR_STALE')
    coverage = plan['coverage']
    for field in ('capture_continuous', 'all_erasure_paths_accounted_for',
                  'all_restore_sources_catalogued', 'legacy_copies_excluded', 'inventory_verified'):
        require(coverage.get(field) is True, 'RESTORE_COVERAGE_INCOMPLETE')
    require(bool(coverage.get('evidence_references')) and coverage.get('gaps') == [],
            'RESTORE_COVERAGE_EVIDENCE_REQUIRED')
    require(all(isinstance(ref, str) and ref.strip() for ref in coverage['evidence_references']),
            'RESTORE_COVERAGE_EVIDENCE_REQUIRED')
    start = timestamp(coverage['from_utc'])
    require(timestamp(coverage['through_utc']) == cutoff, 'RESTORE_COVERAGE_CUTOFF_MISMATCH')
    root = path.parent
    points = plan['points']
    require(set(points) == {'railway', 'auth', 'photos'}, 'RESTORE_ALL_THREE_POINTS_REQUIRED')
    for point in points.values():
        # Conservative snapshot lower bound, independently checked against the
        # original capture receipt/logs. Completion time is not snapshot time.
        snap = timestamp(point['snapshot_not_before_utc'])
        require(now - timedelta(days=MAX_POINT_DAYS) <= snap <= cutoff,
                'RESTORE_RECOVERY_POINT_EXPIRED_OR_INVALID')
        require(start <= snap and bool(point.get('timestamp_evidence')), 'RESTORE_SNAPSHOT_COVERAGE_GAP')
        for item in point['artifacts'].values():
            checked(root, item)
    # Bind conservative bounds to available original receipt times too. An
    # operator may use an earlier bound, never a later-than-completion bound.
    railway_receipt = json.loads(checked(root, points['railway']['artifacts']['receipt']).read_text())
    require(timestamp(points['railway']['snapshot_not_before_utc']) <=
            timestamp(railway_receipt['completed_at_utc']) <= cutoff,
            'RESTORE_SNAPSHOT_RECEIPT_TIME_CONFLICT')
    rp = points['railway']['artifacts']
    require(Path(archive).resolve() == checked(root, rp['archive']) and
            Path(verification).resolve() == checked(root, rp['verification']) and
            Path(receipt_path).resolve() == checked(root, rp['receipt']), 'RESTORE_POINT_ARGUMENT_MISMATCH')
    # Every interval, including an interval with zero erasures, must be present.
    through = start
    keys = set()
    for number, segment in enumerate(plan['segments']):
        require(segment['sequence'] == number and timestamp(segment['from_utc']) == through,
                'RESTORE_JOURNAL_SEGMENT_GAP')
        through = timestamp(segment['through_utc'])
        require(through >= timestamp(segment['from_utc']) and through <= cutoff,
                'RESTORE_JOURNAL_SEGMENT_TIME_INVALID')
        for item in segment['records']:
            require(item['key'] not in keys, 'RESTORE_JOURNAL_DUPLICATE_REFERENCE')
            keys.add(item['key'])
            checked(root, item)
            checked(root, item['receipt'])
    require(bool(plan['segments']) and through == cutoff, 'RESTORE_JOURNAL_SEGMENT_MISSING')
    require(plan['journal_record_count'] == len(keys), 'RESTORE_JOURNAL_INVENTORY_INCOMPLETE')
    return plan, root


def read_events(plan, root, identity):
    events, ids = [], set()
    completed = plan.get('completed_erasure_evidence', {})
    for segment in plan['segments']:
        for item in segment['records']:
            original_receipt = json.loads(checked(root, item['receipt']).read_text())
            require(original_receipt.get('version') == 1 and original_receipt.get('verified') is True and
                    original_receipt.get('key') == item['key'] and
                    original_receipt.get('sha256') == item['sha256'] and
                    original_receipt.get('bytes') == item['bytes'], 'RESTORE_JOURNAL_RECEIPT_INVALID')
            envelope = json.loads(decrypt(checked(root, item), identity))
            require(envelope.get('version') == 1 and envelope.get('source') == b.SOURCE and
                    envelope.get('restore_suppression') is True, 'RESTORE_JOURNAL_ENVELOPE_INVALID')
            event = validate_event(envelope['event'])
            encoded = json.dumps(event, sort_keys=True, separators=(',', ':')).encode()
            fingerprint = hashlib.sha256(encoded).hexdigest()
            require(item['key'] == 'supabase-recovery-v1/deletions/' + fingerprint + '/suppression.json.age',
                    'RESTORE_JOURNAL_EVENT_DIGEST_MISMATCH')
            captured, occurred = timestamp(envelope['captured_at_utc']), timestamp(event['occurred_at_utc'])
            require(timestamp(original_receipt['captured_at_utc']) == captured,
                    'RESTORE_JOURNAL_RECEIPT_TIME_MISMATCH')
            require(timestamp(segment['from_utc']) <= captured <= timestamp(segment['through_utc']) and
                    occurred <= captured, 'RESTORE_JOURNAL_EVENT_TIME_INVALID')
            require(event['event_id'] not in ids, 'RESTORE_JOURNAL_EVENT_ID_CONFLICT')
            ids.add(event['event_id'])
            if event['kind'] == 'account' and event['phase'] == 'requested':
                require(event['event_id'] not in completed, 'RESTORE_REQUEST_ERASURE_PHASE_CONFLICT')
                continue  # An account request is not erasure authorisation.
            proof = completed.get(event['event_id'], {})
            require(proof.get('authorised') is True and proof.get('completed') is True and
                    bool(proof.get('evidence_reference')), 'RESTORE_ERASURE_COMPLETION_UNRESOLVED')
            require(occurred <= timestamp(proof['completed_at_utc']) <= timestamp(plan['cutoff_utc']),
                    'RESTORE_ERASURE_COMPLETION_TIME_INVALID')
            if event['kind'] == 'photo':
                require(type(event.get('user_id')) is int and type(event.get('photo_id')) is int,
                        'RESTORE_PHOTO_OWNER_UNRESOLVED')
            events.append(event)
    require(set(completed) <= ids, 'RESTORE_MISSING_REQUIRED_JOURNAL_EVENT')
    return events


def native_auth(plan, root, identity, values, pg):
    import restore_check
    point = plan['points']['auth']['artifacts']
    verification = json.loads(decrypt(checked(root, point['verification']), identity))
    require(verification.get('version') == 1 and verification.get('password_hashes_in_encrypted_archive') is True,
            'RESTORE_AUTH_VERIFICATION_INVALID')
    receipt = json.loads(checked(root, point['receipt']).read_text())
    require(receipt.get('kind') == 'supabase-independent-recovery' and receipt.get('version') == 1 and
            receipt.get('data_exports_complete') is True, 'RESTORE_SUPABASE_RECEIPT_INVALID')
    require(timestamp(plan['points']['auth']['snapshot_not_before_utc']) <=
            timestamp(verification['created_at_utc']) <= timestamp(receipt['completed_at_utc']) <=
            timestamp(plan['cutoff_utc']), 'RESTORE_AUTH_SNAPSHOT_TIME_CONFLICT')
    # Validate the original transport receipt too, not just the operator inventory.
    for name in ('archive', 'verification'):
        item = point[name]
        require(any(a.get('sha256') == item['sha256'] and a.get('bytes') == item['bytes']
                    for a in receipt['artifacts']), 'RESTORE_AUTH_RECEIPT_MISMATCH')
    with psycopg.connect(**values) as conn:
        require(conn.execute("SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
                             "WHERE n.nspname !~ '^pg_' AND n.nspname<>'information_schema' "
                             "AND c.relkind IN ('r','p','v','m','S','f')").fetchone()[0] == 0,
                'RESTORE_AUTH_TARGET_NOT_EMPTY')
    dec = subprocess.Popen(['age', '--decrypt', '--identity', str(identity), str(checked(root, point['archive']))],
                           stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    writer = None
    try:
        writer = subprocess.Popen(['pg_restore', '--no-owner', '--no-privileges', '--no-password',
                                   '--exit-on-error', '--single-transaction', '--dbname', values['dbname']],
                                  stdin=dec.stdout, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=pg)
        dec.stdout.close()
        require(writer.wait(timeout=1500) == 0 and dec.wait(timeout=30) == 0, 'RESTORE_AUTH_FAILED')
    finally:
        for process in (writer, dec):
            if process and process.poll() is None:
                process.kill(); process.wait(timeout=10)
    from supabase_recovery import fingerprints
    with psycopg.connect(**values) as conn:
        rows = conn.execute("SELECT tablename FROM pg_tables WHERE schemaname='auth' ORDER BY tablename").fetchall()
        expected = verification['tables']
        volatile = verification['intentionally_empty_session_tables']
        require({r[0] for r in rows} == {t['table'] for t in expected} | set(volatile),
                'RESTORE_AUTH_TABLE_INVENTORY_MISMATCH')
        require(fingerprints(conn.cursor(), 'auth', [t['table'] for t in expected]) == expected,
                'RESTORE_AUTH_FINGERPRINT_MISMATCH')
        for name in volatile:
            require(conn.execute(sql.SQL('SELECT count(*) FROM auth.{}').format(sql.Identifier(name))).fetchone()[0] == 0,
                    'RESTORE_AUTH_SESSION_RESTORED')
    return len(expected)


def restore_photos(plan, root, identity):
    from supabase_recovery import OBJECT
    point = plan['points']['photos']['artifacts']
    item = point['archive']
    receipt = json.loads(checked(root, point['receipt']).read_text())
    require(receipt.get('kind') == 'supabase-independent-recovery' and receipt.get('version') == 1 and
            receipt.get('data_exports_complete') is True and any(a.get('sha256') == item['sha256'] and
            a.get('bytes') == item['bytes'] for a in receipt['artifacts']), 'RESTORE_PHOTO_RECEIPT_MISMATCH')
    # Bound RAM usage; larger recovery sets need an explicitly reviewed streaming
    # implementation, never a quiet plaintext spill to persistent disk.
    raw = decrypt(checked(root, item), identity, limit=256 * 1024 * 1024)
    with tarfile.open(fileobj=io.BytesIO(raw), mode='r:') as tar:
        members = tar.getmembers()
        require(len({m.name for m in members}) == len(members) and all(m.isfile() for m in members),
                'RESTORE_PHOTO_TAR_UNSAFE')
        manifest = json.load(tar.extractfile('manifest.json'))
        require(manifest['version'] == 1 and manifest['bucket']['id'] == 'terraces-photos' and
                manifest['bucket']['public'] is False and manifest['source_issuer'] == plan['issuer'],
                'RESTORE_PHOTO_MANIFEST_INVALID')
        require(timestamp(plan['points']['photos']['snapshot_not_before_utc']) <=
                timestamp(manifest['created_at_utc']) <= timestamp(receipt['completed_at_utc']) <=
                timestamp(plan['cutoff_utc']), 'RESTORE_PHOTO_SNAPSHOT_TIME_CONFLICT')
        objects = {}
        for item in manifest['objects']:
            key = item['key']
            require(OBJECT.fullmatch(key) and key not in objects, 'RESTORE_PHOTO_KEY_INVALID')
            data = tar.extractfile('objects/' + key).read()
            require(len(data) == item['bytes'] and hashlib.sha256(data).hexdigest() == item['sha256'],
                    'RESTORE_PHOTO_BYTES_MISMATCH')
            objects[key] = data
        require({m.name for m in members} == {'manifest.json'} | {'objects/' + k for k in objects},
                'RESTORE_PHOTO_UNINVENTORIED_OBJECT')
    return manifest, objects


def replay(rw, auth, events, objects, issuer, cutoff):
    """Validate the complete plan before changes. Failure never permits exposure.

    Transactions cover each isolated DB; cross-DB atomic commit is not claimed.
    A failure in either DB invalidates the whole disposable restore, not a retry
    against a potentially half-committed target. No production mutation path.
    """
    for conn in (rw, auth):
        require(conn.info.host in ('localhost', '127.0.0.1', 'restore-db') and
                conn.info.dbname.startswith('matchgoer_restore_'), 'RESTORE_REPLAY_TARGET_REFUSED')
    account_ids, subjects, photo_keys = set(), set(), set()
    original_links = rw.execute('SELECT user_id,issuer,subject FROM user_identities ORDER BY user_id,issuer,subject').fetchall()
    require(rw.execute('SELECT count(*) FROM terrace_photos p JOIN venue_visits v ON v.visit_id=p.visit_id '
                       'WHERE p.owner_user_id<>v.user_id').fetchone()[0] == 0,
            'RESTORE_PHOTO_VISIT_OWNER_CONFLICT')
    for event in events:
        validate_event(event)
        if event['kind'] == 'photo':
            rows = rw.execute('SELECT photo_id,owner_user_id,display_key,thumbnail_key FROM terrace_photos '
                              'WHERE photo_id=%s OR display_key=ANY(%s) OR thumbnail_key=ANY(%s)',
                              (event['photo_id'], event['object_keys'], event['object_keys'])).fetchall()
            require(all(row[:2] == (event['photo_id'], event['user_id']) and
                        set(row[2:]) == set(event['object_keys']) for row in rows),
                    'RESTORE_PHOTO_IDENTITY_CONFLICT')
            photo_keys.update(event['object_keys'])
            continue
        if event['phase'] == 'requested':
            continue
        uid = event['user_id']
        row = rw.execute('SELECT account_status FROM users WHERE user_id=%s', (uid,)).fetchone()
        require(row is not None, 'RESTORE_ACCOUNT_OWNER_UNRESOLVED')
        expected = {(i['issuer'], i['subject']) for i in event['identities']}
        actual = {(i, s) for u, i, s in original_links if u == uid}
        require(not actual or actual == expected, 'RESTORE_ACCOUNT_IDENTITY_SET_CONFLICT')
        require(actual or row == ('deleted',), 'RESTORE_ACCOUNT_IDENTITY_UNRESOLVED')
        for i, subject in expected:
            require(i == issuer and all(u == uid for u, other_i, other_s in original_links
                    if other_i == i and other_s == subject), 'RESTORE_ACCOUNT_IDENTITY_PAIR_CONFLICT')
            subjects.add(subject)
        account_ids.add(uid)
    for uid in account_ids:
        for keys in rw.execute('SELECT display_key,thumbnail_key FROM terrace_photos WHERE owner_user_id=%s', (uid,)):
            photo_keys.update(keys)
    for key in photo_keys:
        require(rw.execute('SELECT count(*) FROM terrace_photos WHERE display_key=%s OR thumbnail_key=%s',
                           (key, key)).fetchone()[0] <= 1, 'RESTORE_SHARED_PHOTO_KEY_CONFLICT')
    # Snapshot all unrelated account links; no match by email, no orphan repair.
    preserved = [r for r in original_links if r[0] not in account_ids]
    for key in photo_keys:
        rw.execute("UPDATE terrace_photos SET status='REMOVED',published_at=NULL,caption=NULL,"
                   "removed_at=COALESCE(removed_at,%s),storage_deleted_at=COALESCE(storage_deleted_at,%s) "
                   "WHERE display_key=%s OR thumbnail_key=%s", (cutoff, cutoff, key, key))
    for uid in account_ids:
        rw.execute("UPDATE users SET account_status='deleted',is_anonymous=false WHERE user_id=%s", (uid,))
        rw.execute('DELETE FROM user_identities WHERE user_id=%s', (uid,))
        rw.execute('UPDATE anonymous_sessions SET revoked_at=COALESCE(revoked_at,%s) WHERE user_id=%s', (cutoff, uid))
        rw.execute('DELETE FROM account_conversion_handoffs WHERE user_id=%s', (uid,))
        for table in ('fixture_meeting_intents', 'away_day_reviews', 'interested_fixtures', 'venue_visits', 'social_events'):
            rw.execute(sql.SQL('DELETE FROM {} WHERE user_id=%s').format(sql.Identifier(table)), (uid,))
        # Preserve threaded reply FKs while removing public authored content.
        rw.execute("UPDATE match_board_posts SET body='[removed]',deleted_at=COALESCE(deleted_at,%s) WHERE author_user_id=%s", (cutoff, uid))
        rw.execute('DELETE FROM match_board_reports WHERE reporter_user_id=%s', (uid,))
        rw.execute("UPDATE user_profiles SET display_name='Deleted supporter',supported_club=NULL,username=NULL,"
                   "broad_location=NULL,bio=NULL WHERE user_id=%s", (uid,))
    for subject in subjects:
        auth.execute('DELETE FROM auth.users WHERE id=%s', (subject,))
        require(auth.execute('SELECT count(*) FROM auth.identities WHERE user_id=%s', (subject,)).fetchone()[0] == 0,
                'RESTORE_AUTH_PROVIDER_ERASURE_FAILED')
    for key in photo_keys:
        objects.pop(key, None)
        require(key not in objects and rw.execute("SELECT count(*) FROM terrace_photos WHERE "
                "(display_key=%s OR thumbnail_key=%s) AND (status<>'REMOVED' OR storage_deleted_at IS NULL OR published_at IS NOT NULL)",
                (key, key)).fetchone()[0] == 0, 'RESTORE_PHOTO_SUPPRESSION_FAILED')
    for uid in account_ids:
        require(rw.execute("SELECT account_status FROM users WHERE user_id=%s", (uid,)).fetchone() == ('deleted',) and
                rw.execute('SELECT count(*) FROM user_identities WHERE user_id=%s', (uid,)).fetchone()[0] == 0 and
                rw.execute('SELECT count(*) FROM anonymous_sessions WHERE user_id=%s AND revoked_at IS NULL', (uid,)).fetchone()[0] == 0,
                'RESTORE_ACCOUNT_SUPPRESSION_FAILED')
    require(rw.execute('SELECT user_id,issuer,subject FROM user_identities ORDER BY user_id,issuer,subject').fetchall() == preserved,
            'RESTORE_UNRELATED_IDENTITIES_CHANGED')
    require(all(auth.execute('SELECT count(*) FROM auth.users WHERE id=%s', (s,)).fetchone()[0] == 0 for s in subjects),
            'RESTORE_AUTH_ERASURE_FAILED')
    return {'accounts_suppressed': len(account_ids), 'photo_keys_suppressed': len(photo_keys)}


def recover(archive, verification, receipt_path, identity):
    import restore_check
    started = time.monotonic()
    plan, root = load_plan(archive, verification, receipt_path)
    rw_values, _ = restore_check.target()
    auth_values, auth_pg = restore_check.target({**os.environ,
                       'RESTORE_DATABASE_URL': os.environ.get('RESTORE_AUTH_DATABASE_URL', '')})
    require((rw_values['host'], rw_values['port'], rw_values['dbname']) !=
            (auth_values['host'], auth_values['port'], auth_values['dbname']), 'RESTORE_TARGETS_MUST_DIFFER')
    events = read_events(plan, root, identity)
    baseline = restore_check._restore_database(archive, verification, receipt_path, identity)
    auth_tables = native_auth(plan, root, identity, auth_values, auth_pg)
    manifest, objects = restore_photos(plan, root, identity)
    with psycopg.connect(**rw_values) as rw, psycopg.connect(**auth_values) as auth:
        # Verify all current Auth users have precisely one canonical binding;
        # missing Auth users in Railway remain untouched, never silently deleted.
        before_auth = {str(r[0]) for r in auth.execute('SELECT id FROM auth.users')}
        links = rw.execute('SELECT user_id,issuer,subject FROM user_identities').fetchall()
        require(all(sum(i == plan['issuer'] and sub == s for _, i, sub in links) == 1 for s in before_auth),
                'RESTORE_IDENTITY_CONTINUITY_FAILED')
        for photo in manifest['railway_context']['photos']:
            row = rw.execute('SELECT owner_user_id,display_key,thumbnail_key FROM terrace_photos WHERE photo_id=%s',
                             (photo['photo_id'],)).fetchone()
            require(row == (photo['owner_user_id'], photo['display_key'], photo['thumbnail_key']),
                    'RESTORE_PHOTO_OWNER_LINK_MISMATCH')
        known_keys = {k for row in rw.execute('SELECT display_key,thumbnail_key FROM terrace_photos') for k in row}
        require(set(objects) <= known_keys, 'RESTORE_PHOTO_CANONICAL_KEY_UNRESOLVED')
        # A photo removed before a selected snapshot is also suppressed; it need
        # not have a post-snapshot event, but must never be reintroduced by mixing
        # separately timed Railway and photo points.
        prior_removed = set()
        for keys in rw.execute("SELECT display_key,thumbnail_key FROM terrace_photos "
                               "WHERE status='REMOVED' OR storage_deleted_at IS NOT NULL"):
            prior_removed.update(keys)
        for k in prior_removed:
            objects.pop(k, None)
        counts = replay(rw, auth, events, objects, plan['issuer'], timestamp(plan['cutoff_utc']))
        # Tombstones present in the Railway snapshot must never regain Auth via
        # a differently timed Auth snapshot, even if their deletion predates the
        # chosen coverage start. Require explicit journal resolution instead.
        for uid, subject in rw.execute("SELECT u.user_id,i.subject FROM users u JOIN user_identities i USING(user_id) "
                                      "WHERE u.account_status='deleted' AND i.issuer=%s", (plan['issuer'],)):
            require(auth.execute('SELECT count(*) FROM auth.users WHERE id=%s', (subject,)).fetchone()[0] == 0,
                    'RESTORE_DELETED_ACCOUNT_AUTH_CONFLICT')
        # Explicit commits: any failure invalidates BOTH isolated targets.
        rw.commit(); auth.commit()
    return {'passed': True, 'mandatory_journal_replay': True, 'cutoff_utc': plan['cutoff_utc'],
            'inventory_sha256': os.environ['RESTORE_RECOVERY_BUNDLE_SHA256'],
            'tables_verified': baseline['tables_verified'], 'auth_tables_verified': auth_tables,
            'all_row_fingerprints_match': True, 'fingerprints_are_pre_suppression': True,
            'journal_events_replayed': len(events), 'photo_objects_retained': len(objects), **counts,
            'recovery_seconds': round(time.monotonic() - started, 2), 'production_connected': False,
            'private_key_printed_or_copied': False, 'isolated_validation_only': True,
            'cutover_authorised': False, 'session_reauthentication_required': True}
