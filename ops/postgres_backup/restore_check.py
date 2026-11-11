"""Founder-run disposable restore. Private identity file is never copied or printed.

Mount ciphertext and a locally held age identity read-only. Target only an empty,
local database named matchgoer_restore_*. Never mount a production DATABASE_URL.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import time
import urllib.parse

from backup import BackupError, SOURCE, digest, emit


def target(env=os.environ):
    u = urllib.parse.urlsplit(env.get('RESTORE_DATABASE_URL', ''))
    database = urllib.parse.unquote(u.path[1:])
    if (u.scheme not in ('postgres', 'postgresql') or u.hostname not in ('localhost', '127.0.0.1', 'restore-db')
            or not database.startswith('matchgoer_restore_') or u.query or u.fragment):
        raise BackupError('RESTORE_NONDISPOSABLE_TARGET_REFUSED')
    values = {'host': u.hostname, 'port': u.port or 5432, 'dbname': database,
              'user': urllib.parse.unquote(u.username or ''),
              'password': urllib.parse.unquote(u.password or ''), 'connect_timeout': 10}
    pg = {k: env[k] for k in ('PATH', 'SYSTEMROOT', 'LANG') if k in env}
    pg.update(PGHOST=values['host'], PGPORT=str(values['port']), PGDATABASE=database,
              PGUSER=values['user'], PGPASSWORD=values['password'], PGCONNECT_TIMEOUT='10',
              PGAPPNAME='matchgoer-disposable-restore', PGOPTIONS='-c statement_timeout=1200000')
    return values, pg


def validate_receipt(receipt, archive, verification):
    if receipt.get('source') != SOURCE or receipt.get('version') != 1 or receipt.get('verified') is not True:
        raise BackupError('RESTORE_RECEIPT_INVALID')
    for p, size, h in [(archive, receipt['bytes'], receipt['sha256']),
                       (verification, receipt['verification_bytes'], receipt['verification_sha256'])]:
        if p.stat().st_size != size or digest(p) != h:
            raise BackupError('RESTORE_CIPHERTEXT_CHECKSUM_MISMATCH')


def check(archive, verification, receipt_path, identity):
    import psycopg
    from psycopg import sql
    started = time.monotonic()
    values, pg = target()
    receipt = json.loads(receipt_path.read_text())
    validate_receipt(receipt, archive, verification)
    with psycopg.connect(**values) as conn:
        row = conn.execute("SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
                           "WHERE n.nspname !~ '^pg_' AND n.nspname<>'information_schema' "
                           "AND c.relkind IN ('r','p','v','m','S','f')").fetchone()
        if row[0]:
            raise BackupError('RESTORE_TARGET_NOT_EMPTY')
    # No plaintext files; only the encryption tool reads the private identity file.
    manifest = subprocess.run(['age', '--decrypt', '--identity', str(identity), str(verification)],
                              capture_output=True, timeout=60)
    if manifest.returncode:
        raise BackupError('RESTORE_IDENTITY_OR_MANIFEST_INVALID')
    expected = json.loads(manifest.stdout)
    if expected.get('source') != SOURCE or expected.get('version') != 1:
        raise BackupError('RESTORE_VERIFICATION_SOURCE_INVALID')
    decryption = restore = None
    try:
        decryption = subprocess.Popen(['age', '--decrypt', '--identity', str(identity), str(archive)],
                                      stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        restore = subprocess.Popen(['pg_restore', '--no-owner', '--no-privileges', '--no-password',
                                    '--exit-on-error', '--single-transaction', '--dbname', values['dbname']],
                                   stdin=decryption.stdout, stdout=subprocess.DEVNULL,
                                   stderr=subprocess.DEVNULL, env=pg)
        decryption.stdout.close()
        rc = restore.wait(timeout=1500)
        dc = decryption.wait(timeout=30)
        if rc or dc:
            raise BackupError('RESTORE_DATABASE_OR_DECRYPTION_FAILED')
    finally:
        for process in (restore, decryption):
            if process is not None and process.poll() is None:
                process.kill()
                process.wait(timeout=10)
    with psycopg.connect(**values) as conn:
        conn.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
        actual = conn.execute("SELECT n.nspname,c.relname FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
                              "WHERE c.relkind IN ('r','p') AND n.nspname<>'information_schema' "
                              "AND n.nspname !~ '^pg_' ORDER BY 1,2").fetchall()
        expected_names = [(t['schema'], t['table']) for t in expected['tables']]
        if actual != expected_names:
            raise BackupError('RESTORE_TABLE_INVENTORY_MISMATCH')
        for t in expected['tables']:
            count, fingerprint = conn.execute(sql.SQL(
                "SELECT count(*),md5(COALESCE(string_agg(h,'' ORDER BY h),'')) "
                "FROM (SELECT md5(to_jsonb(t)::text) h FROM {}.{} t) q").format(
                    sql.Identifier(t['schema']), sql.Identifier(t['table']))).fetchone()
            if count != t['rows'] or fingerprint != t['fingerprint']:
                raise BackupError('RESTORE_TABLE_FINGERPRINT_MISMATCH')
        conn.rollback()
    return {'passed': True, 'recovery_seconds': round(time.monotonic() - started, 2),
            'tables_verified': len(expected['tables']), 'all_row_fingerprints_match': True,
            'production_connected': False, 'private_key_printed_or_copied': False,
            'note': 'Measured local restore excludes incident diagnosis, downloads and production cutover.'}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--archive', type=Path, required=True)
    parser.add_argument('--verification', type=Path, required=True)
    parser.add_argument('--receipt', type=Path, required=True)
    parser.add_argument('--identity', type=Path, required=True)
    args = parser.parse_args()
    try:
        emit('DISPOSABLE_RESTORE_RESULT', **check(args.archive, args.verification, args.receipt, args.identity))
        return 0
    except Exception as exc:
        emit('DISPOSABLE_RESTORE_FAILED', reason=str(exc) if isinstance(exc, BackupError) else 'RESTORE_OPERATION_FAILED')
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
