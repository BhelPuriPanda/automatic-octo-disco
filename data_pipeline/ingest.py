import os
import sys
import logging
from pathlib import Path
from typing import Optional, Dict
import pandas as pd
from sqlalchemy import text
from sqlalchemy.orm import Session

from config import RAW_DATA_PATH, RANDOM_SEED, DATABASE_URL
from database.connection import get_engine, init_db
from database.models import (
    Product,
    Supplier,
    SupplierProduct,
    Sale,
    Inventory,
    PurchaseOrder
)
from data_pipeline.schema_validation import RawDataValidator
from data_pipeline.cleaner import DataCleaner
from data_pipeline.synthetic_enricher import SyntheticEnricher

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s"
)
logger = logging.getLogger("SupplyChainIQ.Ingest")


class DataIngestionPipeline:
    """
    End-to-end Data Ingestion Pipeline for Phase 1 of SupplyChainIQ:
    Loads Raw CSV -> Validates -> Cleans & Treats Outliers -> Synthetically Enriches -> Ingests into Database.
    """

    def __init__(self, raw_csv_path: Optional[str] = None, db_url: Optional[str] = None, seed: int = RANDOM_SEED):
        self.raw_csv_path = Path(raw_csv_path) if raw_csv_path else RAW_DATA_PATH
        self.db_url = db_url or DATABASE_URL
        self.seed = seed
        self.engine = None

    def run(self) -> Dict[str, int]:
        logger.info("==================================================")
        logger.info("   SUPPLYCHAINIQ - PHASE 1: DATA PIPELINE RUN     ")
        logger.info("==================================================")

        # 1. Check if raw file exists; if not, generate sample raw data
        if not self.raw_csv_path.exists():
            logger.warning(f"Raw CSV file not found at '{self.raw_csv_path}'. Auto-generating realistic raw sample...")
            from sample_data.generate_raw_sample import generate_raw_retail_csv
            self.raw_csv_path = generate_raw_retail_csv(output_path=str(self.raw_csv_path), seed=self.seed)

        logger.info(f"Loading raw dataset from: {self.raw_csv_path.resolve()}")
        try:
            raw_df = pd.read_csv(self.raw_csv_path, encoding="utf-8")
        except UnicodeDecodeError:
            raw_df = pd.read_csv(self.raw_csv_path, encoding="ISO-8859-1")

        logger.info(f"Loaded {len(raw_df)} raw rows. Columns: {list(raw_df.columns)}")

        # 2. Schema Validation
        logger.info("Step 1: Validating raw schema and column aliases...")
        validator = RawDataValidator(raw_df)
        is_valid, mapped_df, val_report = validator.validate()
        
        if not is_valid:
            raise ValueError(f"Schema validation failed: {val_report['missing_columns']}")
        logger.info(f"Schema validation passed! Column mappings: {val_report['column_mapping']}")

        # 3. Data Cleaning and Outlier Handling
        logger.info("Step 2: Cleaning dataset, handling nulls, and treating outliers...")
        cleaner = DataCleaner(mapped_df)
        clean_sales_df, clean_stats = cleaner.clean()

        # 4. Synthetic Supply Chain Enrichment
        logger.info("Step 3: Enriching with supply chain entities (Suppliers, POs, Inventory)...")
        enricher = SyntheticEnricher(seed=self.seed)
        enriched_tables = enricher.enrich(clean_sales_df)

        # 5. Database Connection & Schema Initialization
        logger.info("Step 4: Initializing database schema...")
        self.engine = get_engine(self.db_url)
        init_db(self.engine)

        # 6. Database Load (Atomic Refresh or Insert)
        logger.info("Step 5: Loading clean relational data into database...")
        counts = self._load_tables_to_db(enriched_tables)

        if self.engine:
            self.engine.dispose()

        # 7. Summary
        logger.info("==================================================")
        logger.info("   PHASE 1 DATA INGESTION COMPLETED SUCCESSFULLY!  ")
        logger.info("==================================================")
        for table_name, count in counts.items():
            logger.info(f" - Table '{table_name}': {count:,} records inserted.")

        return counts

    def _load_tables_to_db(self, tables: Dict[str, pd.DataFrame]) -> Dict[str, int]:
        counts = {}
        
        # Load in dependency order
        load_order = [
            ("products", tables["products"]),
            ("suppliers", tables["suppliers"]),
            ("supplier_products", tables["supplier_products"]),
            ("sales", tables["sales"]),
            ("inventory", tables["inventory"]),
            ("purchase_orders", tables["purchase_orders"]),
        ]

        with self.engine.begin() as conn:
            # Clear existing data for clean demo state (in reverse foreign key order)
            for table_name, _ in reversed(load_order):
                conn.execute(text(f"DELETE FROM {table_name};"))

            for table_name, df in load_order:
                df.to_sql(name=table_name, con=conn, if_exists="append", index=False, chunksize=1000)
                counts[table_name] = len(df)

        return counts


if __name__ == "__main__":
    pipeline = DataIngestionPipeline()
    pipeline.run()
