"""Exact-set rollback for the fixed England KNOW Batch 2 population."""

from __future__ import annotations

import argparse
import json
import os

from apply_english_know_batch2 import require_scope
from english_know_batch2_population import execute_rollback, load_pack


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-url", default=os.environ.get("DATABASE_URL"))
    parser.add_argument("--rollback", action="store_true")
    parser.add_argument("--confirm-rollback", action="store_true")
    parser.add_argument("--allow-remote-write", action="store_true")
    args = parser.parse_args()
    if not args.database_url:
        raise RuntimeError("DATABASE_URL is required")
    if not args.rollback or not args.confirm_rollback:
        raise RuntimeError("rollback requires --rollback and --confirm-rollback")
    pack, digest = load_pack()
    url, host_class = require_scope(args.database_url, True, False, args.allow_remote_write)
    result = execute_rollback(url.render_as_string(hide_password=False), pack)
    result.update({"artifact_sha256": digest, "host_class": host_class})
    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
