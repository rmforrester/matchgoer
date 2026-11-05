"""Reproducible isolated regressions. HTTP and hosted database connections forbidden."""
import argparse
import json
import os
from pathlib import Path
import sys
import time
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'backend')]


def main():
    p=argparse.ArgumentParser();p.add_argument('--postgres',action='store_true')
    p.add_argument('--include-timeouts',action='store_true')
    p.add_argument('--output',type=Path,required=True);args=p.parse_args()
    os.environ['DATABASE_URL']='sqlite://'
    os.environ['MATCHGOER_LOCAL_POSTGRES_TEST']='TRUE' if args.postgres else 'FALSE'
    import requests
    def forbidden_http(*a,**kw):raise RuntimeError('Live HTTP disabled in regression tests')
    requests.sessions.Session.request=forbidden_http
    import sqlalchemy
    from sqlalchemy.engine import make_url
    original=sqlalchemy.create_engine
    def local_engine(url,*a,**kw):
        parsed=make_url(url)
        if parsed.get_backend_name()!='sqlite' and not (
            args.postgres and parsed.get_backend_name()=='postgresql' and
            parsed.host=='127.0.0.1' and parsed.port==55439 and
            parsed.username=='fixture_test' and parsed.database=='postgres'):
            raise RuntimeError('Non-test database forbidden')
        return original(url,*a,**kw)
    sqlalchemy.create_engine=local_engine
    def cases(suite):
        for item in suite:
            if isinstance(item,unittest.TestSuite):yield from cases(item)
            else:yield item
    started=time.monotonic()
    suite=unittest.defaultTestLoader.discover(str(ROOT/'ingestion/tests'),pattern='test_*.py')
    suite=unittest.TestSuite(t for t in cases(suite) if args.include_timeouts or
                            'test_fixture_precommit_postgres.' not in t.id())
    args.output.mkdir(parents=True,exist_ok=True)
    with (args.output/'final-regression-tests.log').open('w',encoding='utf-8') as log:
        from contextlib import redirect_stdout
        with redirect_stdout(log):result=unittest.TextTestRunner(stream=log,verbosity=2).run(suite)
    summary=dict(tests=result.testsRun,failures=len(result.failures),errors=len(result.errors),
        skipped=len(result.skipped),passed=result.wasSuccessful(),elapsed_seconds=round(time.monotonic()-started,2),
        live_http=False,hosted_access=False,postgres_loopback_only=args.postgres,
        unchanged_timeout_suite_included=args.include_timeouts)
    (args.output/'final-test-summary.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
    print(json.dumps(summary))
    return int(not result.wasSuccessful())


if __name__=='__main__':raise SystemExit(main())
