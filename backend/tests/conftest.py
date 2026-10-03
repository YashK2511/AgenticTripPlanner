import pytest
from app.core.database import init_db, SessionLocal, engine, Base
from app.data.seed_pois import seed_database

@pytest.fixture(scope="session", autouse=True)
def setup_test_db():
    # Initialize all tables (including poi_embeddings)
    Base.metadata.create_all(bind=engine)

    # Seed initial test data
    db = SessionLocal()
    try:
        seed_database(db)
    finally:
        db.close()

    yield
