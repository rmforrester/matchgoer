import os
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

dotenv_path = Path(__file__).parent / ".env"

print("Looking for:", dotenv_path)
print("Exists:", dotenv_path.exists())

load_dotenv(dotenv_path)

DATABASE_URL = os.getenv("DATABASE_URL")
print("DATABASE_URL =", DATABASE_URL)

engine = create_engine(DATABASE_URL)

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)