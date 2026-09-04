import logging
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker
from config import DATABASE_URL, DEFAULT_SQLITE_URL, USE_SQLITE_FALLBACK

logger = logging.getLogger(__name__)

Base = declarative_base()

def get_engine(db_url: str = DATABASE_URL):
    """
    Creates and returns a SQLAlchemy engine.
    If PostgreSQL connection fails and USE_SQLITE_FALLBACK is True,
    it falls back to a local SQLite database for smooth testing/demoing.
    """
    try:
        engine = create_engine(db_url, echo=False, pool_pre_ping=True)
        # Test connection
        with engine.connect() as conn:
            logger.info(f"Successfully connected to database: {engine.url.render_as_string(hide_password=True)}")
        return engine
    except Exception as e:
        if USE_SQLITE_FALLBACK and "postgresql" in db_url:
            logger.warning(f"PostgreSQL connection failed ({e}). Falling back to SQLite for local development/demo.")
            engine = create_engine(DEFAULT_SQLITE_URL, echo=False)
            return engine
        else:
            raise e

def get_session(engine=None):
    """
    Returns a new database session.
    """
    if engine is None:
        engine = get_engine()
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    return SessionLocal()

def init_db(engine=None):
    """
    Initializes database tables defined in models.py.
    """
    if engine is None:
        engine = get_engine()
    
    # Import models so that Base.metadata knows about all tables
    import database.models  # noqa: F401
    Base.metadata.create_all(bind=engine)
    logger.info("All database tables verified/created successfully.")
    return engine
