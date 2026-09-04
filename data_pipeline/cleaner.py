import logging
from typing import Tuple, Dict
import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)


class DataCleaner:
    """
    Cleans raw retail transaction data:
    1. Standardizes date formats and timezones
    2. Strips whitespace and normalizes text fields
    3. Handles missing values (imputation & sensible defaults)
    4. Detects and handles negative quantities/returns
    5. Detects and treats price and demand outliers using statistical thresholds
    6. Generates clean transactional metrics (total_revenue)
    """

    def __init__(self, df: pd.DataFrame):
        self.raw_df = df.copy()
        self.cleaning_stats = {
            "initial_rows": len(df),
            "rows_missing_key_fields": 0,
            "returns_cancellations_filtered": 0,
            "zero_or_negative_price_rows": 0,
            "quantity_outliers_capped": 0,
            "missing_descriptions_imputed": 0,
            "missing_customer_ids_imputed": 0,
            "final_clean_sales_rows": 0,
        }

    def clean(self) -> Tuple[pd.DataFrame, Dict]:
        df = self.raw_df.copy()

        # 1. Clean string fields and whitespace
        for col in ["sku", "product_name", "invoice_id", "customer_id", "country"]:
            if col in df.columns:
                df[col] = df[col].astype(str).str.strip()
                df[col] = df[col].replace(["nan", "None", "NULL", "null", ""], np.nan)

        if "sku" in df.columns:
            df["sku"] = df["sku"].str.upper()

        # 2. Standardize dates
        logger.info("Standardizing sale dates...")
        initial_date_nulls = df["sale_date"].isna().sum()
        df["sale_date"] = pd.to_datetime(df["sale_date"], format="mixed", errors="coerce")
        invalid_dates = df["sale_date"].isna().sum() - initial_date_nulls
        if invalid_dates > 0:
            logger.warning(f"Coerced {invalid_dates} unparseable date values to NaT.")

        # 3. Numeric conversion
        df["quantity"] = pd.to_numeric(df["quantity"], errors="coerce")
        df["unit_price"] = pd.to_numeric(df["unit_price"], errors="coerce")

        # 4. Drop rows with null essential identifiers
        essential_cols = ["sku", "sale_date", "quantity", "unit_price"]
        null_mask = df[essential_cols].isna().any(axis=1)
        self.cleaning_stats["rows_missing_key_fields"] = int(null_mask.sum())
        df = df[~null_mask].copy()

        # 5. Handle Returns and Cancellations
        # In retail datasets (like UCI), returns start with 'C' in InvoiceNo or have negative quantity
        return_mask = (df["quantity"] <= 0) | (df["invoice_id"].str.startswith("C", na=False))
        self.cleaning_stats["returns_cancellations_filtered"] = int(return_mask.sum())
        # Filter for positive demand/sales transactions (for baseline demand pipeline)
        sales_df = df[~return_mask].copy()

        # 6. Filter zero or negative unit prices
        bad_price_mask = sales_df["unit_price"] <= 0
        self.cleaning_stats["zero_or_negative_price_rows"] = int(bad_price_mask.sum())
        sales_df = sales_df[~bad_price_mask].copy()

        # 7. Impute missing descriptions by SKU lookup
        sku_desc_map = (
            sales_df.dropna(subset=["product_name"])
            .groupby("sku")["product_name"]
            .agg(lambda s: s.mode().iloc[0] if not s.empty else "Unknown Product")
            .to_dict()
        )

        missing_desc_mask = sales_df["product_name"].isna()
        self.cleaning_stats["missing_descriptions_imputed"] = int(missing_desc_mask.sum())
        sales_df["product_name"] = sales_df.apply(
            lambda row: sku_desc_map.get(row["sku"], f"Item {row['sku']}") if pd.isna(row["product_name"]) else row["product_name"],
            axis=1
        )

        # 8. Impute missing customer IDs and countries
        if "customer_id" in sales_df.columns:
            missing_cust = sales_df["customer_id"].isna()
            self.cleaning_stats["missing_customer_ids_imputed"] = int(missing_cust.sum())
            sales_df["customer_id"] = sales_df["customer_id"].fillna("CUST-GUEST")

        if "country" in sales_df.columns:
            sales_df["country"] = sales_df["country"].fillna("Domestic")

        # 9. Outlier treatment for extreme demand spikes (IQR per SKU)
        # Cap demand spikes at Q3 + 3 * IQR to prevent model skewing while retaining valid variability
        outliers_capped = 0
        for sku, group in sales_df.groupby("sku"):
            q25 = group["quantity"].quantile(0.25)
            q75 = group["quantity"].quantile(0.75)
            iqr = q75 - q25
            upper_bound = q75 + 3.0 * iqr
            
            # Floor upper bound at minimum 20 units so regular high orders aren't artificially flattened
            upper_bound = max(upper_bound, 20.0)

            high_mask = (sales_df["sku"] == sku) & (sales_df["quantity"] > upper_bound)
            num_high = high_mask.sum()
            if num_high > 0:
                sales_df.loc[high_mask, "quantity"] = int(upper_bound)
                outliers_capped += num_high

        self.cleaning_stats["quantity_outliers_capped"] = int(outliers_capped)

        # 10. Compute derived financial fields
        sales_df["quantity"] = sales_df["quantity"].astype(int)
        sales_df["unit_price"] = sales_df["unit_price"].round(2)
        sales_df["total_revenue"] = (sales_df["quantity"] * sales_df["unit_price"]).round(2)

        # Ensure consistent sale_id
        if "invoice_id" in sales_df.columns:
            sales_df["sale_id"] = sales_df["invoice_id"] + "-" + sales_df.groupby("invoice_id").cumcount().astype(str)
        else:
            sales_df["sale_id"] = "SALE-" + sales_df.index.astype(str)

        self.cleaning_stats["final_clean_sales_rows"] = len(sales_df)
        logger.info(f"Data cleaning complete: {self.cleaning_stats}")
        return sales_df, self.cleaning_stats
