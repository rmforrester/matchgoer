import argparse
import json
from pathlib import Path

from database import SessionLocal
from decide_inventory import (
    load_identity_inventory, read_inventory, reconcile_row, summary, write_publication_sql,
    write_publication_summary, write_reconciliation,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only DECIDE editorial inventory reconciliation")
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--publication-sql", type=Path)
    parser.add_argument("--dry-run-report", type=Path)
    args = parser.parse_args()

    source_rows = read_inventory(args.inventory)
    db = SessionLocal()
    try:
        identities = load_identity_inventory(db)
        rows = [reconcile_row(row, identities) for row in source_rows]
    finally:
        db.rollback()
        db.close()
    write_reconciliation(args.output, rows)
    if args.publication_sql:
        write_publication_sql(args.publication_sql, rows)
    if args.dry_run_report:
        write_publication_summary(args.dry_run_report, rows, args.output)
    print(json.dumps(summary(rows), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
