import argparse
import json
from pathlib import Path

from database import SessionLocal
from decide_inventory import load_identity_inventory, read_inventory, reconcile_row, summary, write_reconciliation


def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only DECIDE editorial inventory reconciliation")
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
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
    print(json.dumps(summary(rows), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
