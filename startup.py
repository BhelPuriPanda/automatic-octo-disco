"""
startup.py — Render First-Boot Initializer
Runs the full data pipeline (Phases 1-5) the first time the service starts.
If the database already has data, this is a no-op (fast re-deploy).
"""
import sys
import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("startup")

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

from config import DATABASE_URL
from database.connection import get_engine, init_db
from sqlalchemy import text


def tables_populated(engine) -> bool:
    """Returns True if the products table already has rows."""
    try:
        with engine.connect() as conn:
            result = conn.execute(text("SELECT COUNT(*) FROM products")).scalar()
            return result > 0
    except Exception:
        return False


def main():
    logger.info("=== SupplyChainIQ Startup Bootstrap ===")
    logger.info(f"Database: {DATABASE_URL[:50]}...")

    engine = get_engine(DATABASE_URL)
    init_db(engine)

    if tables_populated(engine):
        logger.info("Database already populated — skipping pipeline. Ready to serve.")
        return

    logger.info("Empty database detected — running full pipeline (Phases 1-5)...")

    # ── Phase 1: Data Ingestion ──────────────────────────────────────────────
    from data_pipeline.ingest import DataIngestionPipeline
    pipeline = DataIngestionPipeline(db_url=DATABASE_URL)
    pipeline.run()
    logger.info("Phase 1 complete.")

    # ── Phase 2: Demand Forecasting ──────────────────────────────────────────
    # Constructor: ForecastingEngine(db_url, test_days, forecast_horizon_days)
    # Method:      .execute_and_persist()
    from forecasting.engine import ForecastingEngine
    fe = ForecastingEngine(db_url=DATABASE_URL, test_days=30, forecast_horizon_days=30)
    fe.execute_and_persist()
    logger.info("Phase 2 complete.")

    # ── Phase 3: Inventory Optimization ──────────────────────────────────────
    # Constructor: InventoryOptimizer(db_url, default_service_level)
    # Method:      .optimize_all_products()
    from inventory_optimization.optimizer import InventoryOptimizer
    io = InventoryOptimizer(db_url=DATABASE_URL, default_service_level=0.95)
    io.optimize_all_products()
    logger.info("Phase 3 complete.")

    # ── Phase 4: Replenishment ────────────────────────────────────────────────
    # Constructor: ReplenishmentPlanner(db_url)
    # Method:      .run_plan()
    from replenishment_analytics.replenishment import ReplenishmentPlanner
    rp = ReplenishmentPlanner(db_url=DATABASE_URL)
    rp.run_plan()
    logger.info("Phase 4 complete.")

    # ── Phase 5: Supplier Scorecard ───────────────────────────────────────────
    # Constructor: SupplierScorecardEngine(db_url)
    # Method:      .generate_scorecard()
    from supplier_scorecard.engine import SupplierScorecardEngine
    ss = SupplierScorecardEngine(db_url=DATABASE_URL)
    ss.generate_scorecard()
    logger.info("Phase 5 complete.")

    logger.info("=== Bootstrap Complete. API server starting... ===")


if __name__ == "__main__":
    main()
