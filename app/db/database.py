from typing import Generator
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, Session
import logfire

from app.config import settings

# Initialize SQLAlchemy Engine with connection pooling and pre-ping
engine = create_engine(
    settings.DATABASE_URL,
    pool_size=settings.DB_POOL_SIZE,
    max_overflow=settings.DB_MAX_OVERFLOW,
    pool_timeout=settings.DB_POOL_TIMEOUT,
    pool_recycle=settings.DB_POOL_RECYCLE,
    pool_pre_ping=True,
    echo=False
)

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
    expire_on_commit=False
)


def get_db() -> Generator[Session, None, None]:
    """
    FastAPI dependency for request-scoped database sessions.
    Automatically rolls back uncommitted changes on exceptions and closes the session.
    """
    db = SessionLocal()
    try:
        yield db
    except Exception as e:
        db.rollback()
        logfire.error(f"Database session error: {e}")
        raise
    finally:
        db.close()


def check_db_health() -> bool:
    """
    Check if the PostgreSQL database is reachable and responsive.
    """
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception as e:
        logfire.warning(f"PostgreSQL health check failed: {e}")
        return False
