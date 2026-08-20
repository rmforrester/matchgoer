"""Environment loading shared by the ingestion commands."""

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def backend_environment() -> dict[str, str]:
    values = read_env_file(ROOT / "backend" / ".env")
    values.update({key: value for key, value in os.environ.items() if value})
    return values


def database_url() -> str:
    value = backend_environment().get("DATABASE_URL")
    if not value:
        raise RuntimeError("DATABASE_URL is required in backend/.env or the environment.")
    return value


def api_football_key() -> str:
    environment = backend_environment()
    for name in ("API_FOOTBALL_KEY", "API_SPORTS_KEY"):
        if environment.get(name):
            return environment[name]
    raise RuntimeError("API_FOOTBALL_KEY is required in backend/.env or the environment; legacy hard-coded keys are not used.")
