"""
startup.py — Render First-Boot Initializer
Runs the full data pipeline (Phases 1-5) the first time the service starts.
If the database already has data, this is a no-op.
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
    try:
        with engine.connect() as conn:
            result = conn.execute(text("SELECT COUNT(*) FROM products")).scalar()
            return result > 0
    except Exception:
        return False

def main():
    logger.info("=== SupplyChainIQ Startup Bootstrap ===")
    logger.info(f"Database URL: {DATABASE_URL[:40]}...")

    engine = get_engine(DATABASE_URL)
    init_db(engine)

    if tables_populated(engine):
        logger.info("Database already populated — skipping pipeline. Ready to serve.")
        return

    logger.info("Empty database detected — running full pipeline (Phases 1-5)...")

    # Phase 1: Data Ingestion
    from data_pipeline.ingest import DataIngestionPipeline
    pipeline = DataIngestionPipeline(DATABASE_URL)
    pipeline.run()
    logger.info("Phase 1 complete.")

    # Phase 2: Forecasting
    from forecasting.engine import ForecastingEngine
    fe = ForecastingEngine(DATABASE_URL)
    fe.run_all(test_days=30, horizon=30)
    logger.info("Phase 2 complete.")

    # Phase 3: Inventory Optimization
    from inventory_optimization.optimizer import InventoryOptimizer
    io = InventoryOptimizer(DATABASE_URL)
    io.run(service_level=0.95)
    logger.info("Phase 3 complete.")

    # Phase 4: Replenishment
    from replenishment_analytics.replenishment import ReplenishmentPlanner
    rp = ReplenishmentPlanner(DATABASE_URL)
    rp.run()
    logger.info("Phase 4 complete.")

    # Phase 5: Supplier Scorecard
    from supplier_scorecard.engine import SupplierScorecardEngine
    ss = SupplierScorecardEngine(DATABASE_URL)
    ss.run()
    logger.info("Phase 5 complete.")

    logger.info("=== Bootstrap Complete. API server starting... ===")

if __name__ == "__main__":
    main()
