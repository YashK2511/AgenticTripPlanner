from sqlalchemy import create_engine
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


def init_db():
    """
    Create all tables in the database.
    Call this on application startup.
    """
    logger.info("Initializing database schema")
    Base.metadata.create_all(bind=engine)
    logger.info("Database schema created")
