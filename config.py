import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

# Database URL with automatic SQLite fallback for testing/demo environments
DEFAULT_POSTGRES_URL = "postgresql+psycopg2://postgres:postgres@localhost:5432/supplychainiq"
DEFAULT_SQLITE_URL = f"sqlite:///{BASE_DIR / 'supplychainiq.db'}"

_raw_db_url = os.getenv("DATABASE_URL", DEFAULT_POSTGRES_URL)

# Render (and Heroku) inject `postgres://` which SQLAlchemy 2.0 rejects.
# Rewrite it to the correct `postgresql+psycopg2://` dialect.
if _raw_db_url.startswith("postgres://"):
    _raw_db_url = _raw_db_url.replace("postgres://", "postgresql+psycopg2://", 1)
elif _raw_db_url.startswith("postgresql://") and "+" not in _raw_db_url:
    _raw_db_url = _raw_db_url.replace("postgresql://", "postgresql+psycopg2://", 1)

DATABASE_URL = _raw_db_url
USE_SQLITE_FALLBACK = os.getenv("USE_SQLITE_FALLBACK", "true").lower() in ("true", "1", "yes")

# Pipeline settings
RAW_DATA_PATH = Path(os.getenv("RAW_DATA_PATH", BASE_DIR / "sample_data" / "raw_retail_sales.csv"))
RANDOM_SEED = int(os.getenv("RANDOM_SEED", 42))

# Logging setup
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
