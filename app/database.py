from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


DATABASE_URL = "postgresql://postgres:Spurley3!@localhost:5432/terrace_talk"


engine = create_engine(DATABASE_URL)

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine
)