"""Independent read-only missed-run check. Never invokes reconciliation or provider APIs."""
import argparse
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sqlalchemy import create_engine, select
from sqlalchemy.engine import make_url
from backend.fixture_integrity import RUNS, missed_run


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--database-env', default='DATABASE_URL')
    parser.add_argument('--grace-hours', type=float, default=2)
    args = parser.parse_args()
    if not 0 <= args.grace_hours <= 12:
        parser.error('grace must be between 0 and 12 hours')
    engine = None
    try:
        url = make_url(os.environ[args.database_env])
        existing_options = url.query.get('options', '')
        engine = create_engine(url, connect_args={
            'options': existing_options+' -c default_transaction_read_only=on -c statement_timeout=15000 -c lock_timeout=3000'})
        now = datetime.now(timezone.utc)
        with engine.connect() as connection:
            rows = [dict(r) for r in connection.execute(select(RUNS).where(
                RUNS.c.scheduled_for >= now-timedelta(days=3))).mappings()]
            connection.rollback()
        result = missed_run(rows, now=now, grace_hours=args.grace_hours)
        print(json.dumps(result))
        return 0 if result['passed'] else 1
    except Exception as error:
        print(json.dumps(dict(passed=False,reason='INTEGRITY_MONITOR_UNAVAILABLE',error_type=type(error).__name__)))
        return 2
    finally:
        if engine is not None:
            engine.dispose()


if __name__ == '__main__':
    raise SystemExit(main())
