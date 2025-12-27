import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import StaticPool

# Import your models
from hardware_agent.db import schema


@pytest.fixture(scope="session")
def db_engine():
    """Create a test database engine"""
    # Use in-memory SQLite for fast tests
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    schema.metadata.create_all(engine)
    yield engine
    schema.metadata.drop_all(engine)


@pytest.fixture(scope="function")
def db_session(db_engine):
    """Create a new database session for each test"""
    connection = db_engine.connect()
    transaction = connection.begin()
    session = sessionmaker(bind=connection)()

    yield session

    session.close()
    transaction.rollback()
    connection.close()
