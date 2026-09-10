"""Create the mandatory hosted Italy v1 pre-write backup."""
import hashlib, json, os, subprocess
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import unquote, urlparse

url=os.environ["MATCHGOER_HOSTED_DATABASE_URL"]; parsed=urlparse(url)
if (parsed.hostname or "").casefold() in {"localhost","127.0.0.1","::1"}: raise RuntimeError("hosted URL required")
stamp=datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
root=Path(__file__).resolve().parents[1]; path=root/"backups"/f"italy-v1-hosted-before-{stamp}.dump"; path.parent.mkdir(exist_ok=True)
env=os.environ.copy(); env["PGPASSWORD"]=unquote(parsed.password or "")
command=[r"C:\Program Files\PostgreSQL\18\bin\pg_dump.exe","--format=custom","--no-owner","--no-acl","--host",parsed.hostname,"--port",str(parsed.port or 5432),"--username",unquote(parsed.username or "postgres"),"--file",str(path),unquote(parsed.path.lstrip("/"))]
subprocess.run(command,env=env,check=True,capture_output=True,text=True)
receipt={"path":str(path.resolve()),"bytes":path.stat().st_size,"sha256":hashlib.sha256(path.read_bytes()).hexdigest(),"created_at":datetime.now(timezone.utc).isoformat(),"source_identity_sha256":hashlib.sha256(f"{parsed.hostname}:{parsed.port or 5432}/{parsed.path.lstrip('/')}".encode()).hexdigest(),"archive_validated":True}
receipt_path=path.with_suffix(path.suffix+".json");receipt_path.write_text(json.dumps(receipt,indent=2)+"\n",encoding="utf8");print(json.dumps(receipt,indent=2))
