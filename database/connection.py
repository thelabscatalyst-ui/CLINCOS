from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from config import settings

engine = create_engine(
    settings.DATABASE_URL,
    connect_args={"check_same_thread": False} if "sqlite" in settings.DATABASE_URL else {},
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def create_tables():
    from database import models  # noqa: F401 — ensures models are registered
    Base.metadata.create_all(bind=engine)
    _run_migrations()


def _run_migrations():
    """Apply additive schema migrations that create_all() won't handle."""
    with engine.connect() as conn:
        # Tier 1: pin_hash column on doctors (nullable — existing rows stay valid)
        try:
            conn.execute(
                __import__("sqlalchemy").text(
                    "ALTER TABLE doctors ADD COLUMN pin_hash VARCHAR(255)"
                )
            )
            conn.commit()
        except Exception:
            pass  # column already exists — safe to ignore
