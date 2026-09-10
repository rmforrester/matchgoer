"""Create the mandatory local Italy v1 pre-write backup without exposing credentials."""
from datetime import datetime, timezone
from pathlib import Path
from backend.database import engine
from backend.know_v1_local_acceptance import backup

url = engine.url.set(database="matchgoer_btm_v2_local_20260907").render_as_string(hide_password=False)
stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
path = Path(__file__).resolve().parents[1] / "backups" / f"italy-v1-local-before-{stamp}.dump"
print(backup(url, path, Path(r"C:\Program Files\PostgreSQL\18\bin\pg_dump.exe")))
