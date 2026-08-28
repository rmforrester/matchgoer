"""Validate, dry-run, publish, or roll back one hash-approved KNOW candidate."""

import argparse
import json
import os

from sqlalchemy.engine import make_url

from know_population import dry_run, execute_rollback, execute_write, load_candidate

LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}


def require_scope(database_url, action, allow_remote_audit, allow_remote_write):
    url = make_url(database_url)
    remote = url.host not in LOCAL_HOSTS
    write = action in {"write", "rollback"}
    if remote and write and not allow_remote_write:
        raise RuntimeError("remote write refused without --allow-remote-write")
    if remote and not write and not allow_remote_audit:
        raise RuntimeError("remote dry run refused without --allow-remote-audit")
    if not remote and (allow_remote_audit or allow_remote_write):
        raise RuntimeError("remote intent flag supplied for local database")
    return url, "remote" if remote else "local"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", required=True)
    parser.add_argument("--expected-sha256", required=True)
    parser.add_argument("--expected-version", required=True)
    parser.add_argument("--database-url", default=os.environ.get("DATABASE_URL"))
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--confirm-write", action="store_true")
    parser.add_argument("--rollback", action="store_true")
    parser.add_argument("--confirm-rollback", action="store_true")
    parser.add_argument("--allow-remote-audit", action="store_true")
    parser.add_argument("--allow-remote-write", action="store_true")
    args = parser.parse_args()
    if not args.database_url:
        raise RuntimeError("DATABASE_URL is required")
    if args.write != args.confirm_write or args.rollback != args.confirm_rollback:
        raise RuntimeError("write/rollback requires its matching confirmation flag")
    if args.write and args.rollback:
        raise RuntimeError("write and rollback are mutually exclusive")
    action = "write" if args.write else "rollback" if args.rollback else "dry-run"
    candidate = load_candidate(args.candidate, expected_sha256=args.expected_sha256, expected_version=args.expected_version)
    url, host_class = require_scope(args.database_url, action, args.allow_remote_audit, args.allow_remote_write)
    database_url = url.render_as_string(hide_password=False)
    result = execute_write(database_url, candidate) if action == "write" else execute_rollback(database_url, candidate) if action == "rollback" else dry_run(database_url, candidate)
    result.update({"artifact_sha256": candidate.sha256, "artifact_version": candidate.version,
                   "host_class": host_class, "action": action})
    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
