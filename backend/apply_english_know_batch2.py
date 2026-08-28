"""Dry-run or apply the fixed England KNOW Batch 2 publication candidate."""

from __future__ import annotations

import argparse
import json
import os

from sqlalchemy.engine import make_url

from english_know_batch2_population import (
    LOCAL_HOSTS,
    dry_run,
    execute_write,
    load_pack,
)


def require_mode(write, confirm_write):
    if write != confirm_write:
        raise RuntimeError("write requires both --write and --confirm-write")
    return write


def require_scope(database_url, write, allow_remote_audit, allow_remote_write):
    url = make_url(database_url)
    remote = url.host not in LOCAL_HOSTS
    if remote and write and not allow_remote_write:
        raise RuntimeError("remote write refused without --allow-remote-write")
    if remote and not write and not allow_remote_audit:
        raise RuntimeError("remote dry run refused without --allow-remote-audit")
    if not remote and (allow_remote_audit or allow_remote_write):
        raise RuntimeError("remote intent flag supplied for local database")
    return url, "remote" if remote else "local"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-url", default=os.environ.get("DATABASE_URL"))
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--confirm-write", action="store_true")
    parser.add_argument("--allow-remote-audit", action="store_true")
    parser.add_argument("--allow-remote-write", action="store_true")
    args = parser.parse_args()
    if not args.database_url:
        raise RuntimeError("DATABASE_URL is required")
    pack, digest = load_pack()
    write = require_mode(args.write, args.confirm_write)
    url, host_class = require_scope(args.database_url, write, args.allow_remote_audit, args.allow_remote_write)
    result = execute_write(url.render_as_string(hide_password=False), pack) if write else dry_run(url.render_as_string(hide_password=False), pack)
    result.update({"artifact_sha256": digest, "host_class": host_class, "write": write})
    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
