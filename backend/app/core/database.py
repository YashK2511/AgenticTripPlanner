from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, declarative_base
from app.core.config import settings
import logging

logger = logging.getLogger("trip_planner.db")

# Create the engine
engine = create_engine(
    settings.database_url,
    echo=settings.DEBUG,
    connect_args={"check_same_thread": False} if settings.USE_SQLITE else {},
)

# Create session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base class for all ORM models
Base = declarative_base()


def get_db():
    """
    Dependency for FastAPI routes to get a database session.
    Usage:
        @app.get("/items")
        def list_items(db: Session = Depends(get_db)):
            return db.query(Item).all()
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _migrate_trip_states_schema(conn):
    """
    Idempotent schema migration to add columns introduced after the initial table creation.
    Supports both SQLite (PRAGMA inspection) and PostgreSQL (information_schema query).
    """
    if settings.USE_SQLITE:
        rows = conn.execute(text("PRAGMA table_info(trip_states);")).fetchall()
        existing_columns = {row[1] for row in rows}
        if "context_json" not in existing_columns:
            logger.info("Migrating schema: adding context_json column to trip_states (SQLite)")
            conn.execute(text("ALTER TABLE trip_states ADD COLUMN context_json JSON;"))
            conn.commit()
    else:
        # PostgreSQL path — check information_schema
        row = conn.execute(
            text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name='trip_states' AND column_name='context_json';"
            )
        ).fetchone()
        if row is None:
            logger.info("Migrating schema: adding context_json column to trip_states (PostgreSQL)")
            conn.execute(text("ALTER TABLE trip_states ADD COLUMN context_json JSON;"))
            conn.commit()


def init_db():
    """
    Create all tables in the database and run non-destructive column migrations.
    Call this on application startup.
    """
    logger.info("Initializing database schema")
    Base.metadata.create_all(bind=engine)

    with engine.connect() as conn:
        _migrate_trip_states_schema(conn)

    logger.info("Database schema verified")
