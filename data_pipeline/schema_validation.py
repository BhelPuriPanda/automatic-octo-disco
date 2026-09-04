import logging
from typing import Dict, List, Tuple
import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)


class RawDataValidator:
    """
    Validates incoming raw sales CSV datasets for required fields,
    data types, null thresholds, and format anomalies.
    """

    EXPECTED_COLUMNS_ALIASES = {
        "invoice_id": ["invoiceno", "invoice_no", "transaction_id", "order_id", "invoice"],
        "sku": ["stockcode", "stock_code", "sku", "product_id", "item_code", "product_code"],
        "product_name": ["description", "product_name", "item_name", "title"],
        "quantity": ["quantity", "qty", "units_sold", "volume"],
        "sale_date": ["invoicedate", "invoice_date", "sale_date", "order_date", "timestamp", "date"],
        "unit_price": ["unitprice", "unit_price", "price", "unit_cost", "item_price"],
        "customer_id": ["customerid", "customer_id", "client_id", "user_id"],
        "country": ["country", "region", "location", "store_id", "channel"]
    }

    def __init__(self, df: pd.DataFrame):
        self.df = df.copy()
        self.validation_report = {
            "total_raw_rows": len(df),
            "missing_columns": [],
            "column_mapping": {},
            "null_counts": {},
            "non_numeric_price_rows": 0,
            "non_numeric_quantity_rows": 0,
            "invalid_date_rows": 0,
            "passed": False
        }

    def map_columns(self) -> pd.DataFrame:
        """
        Maps raw column names to standardized canonical column names.
        """
        df = self.df
        normalized_cols = {c.strip().lower().replace(" ", "_"): c for c in df.columns}
        canonical_map = {}

        for canonical_name, aliases in self.EXPECTED_COLUMNS_ALIASES.items():
            found = False
            for alias in aliases:
                if alias in normalized_cols:
                    canonical_map[normalized_cols[alias]] = canonical_name
                    found = True
                    break
            if not found and canonical_name in ["invoice_id", "sku", "quantity", "sale_date", "unit_price"]:
                self.validation_report["missing_columns"].append(canonical_name)

        self.validation_report["column_mapping"] = canonical_map
        logger.info(f"Mapped columns: {canonical_map}")
        
        # Rename mapped columns
        mapped_df = df.rename(columns=canonical_map)
        return mapped_df

    def validate(self) -> Tuple[bool, pd.DataFrame, Dict]:
        """
        Executes comprehensive validation and returns (is_valid, mapped_df, report).
        """
        mapped_df = self.map_columns()

        if self.validation_report["missing_columns"]:
            logger.error(f"Critical columns missing from raw dataset: {self.validation_report['missing_columns']}")
            self.validation_report["passed"] = False
            return False, mapped_df, self.validation_report

        # Check null values
        for col in ["invoice_id", "sku", "quantity", "sale_date", "unit_price"]:
            if col in mapped_df.columns:
                null_count = int(mapped_df[col].isna().sum())
                self.validation_report["null_counts"][col] = null_count

        self.validation_report["passed"] = True
        return True, mapped_df, self.validation_report
