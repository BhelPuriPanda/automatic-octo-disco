"""
SupplyChainIQ - Phase 1 Runner Script
Executes the data pipeline end-to-end, prints database tables summary, and displays sample queries.
"""

import argparse
import sys
import pandas as pd
from sqlalchemy import text
from config import DATABASE_URL, RAW_DATA_PATH
from database.connection import get_engine
from data_pipeline.ingest import DataIngestionPipeline


def display_database_summary(engine):
    print("\n" + "=" * 65)
    print("         SUPPLYCHAINIQ DATABASE SCHEMA & RECORD COUNTS         ")
    print("=" * 65)

    tables = [
        "products",
        "suppliers",
        "supplier_products",
        "sales",
        "inventory",
        "purchase_orders",
        "forecasts",
        "inventory_metrics",
    ]

    with engine.connect() as conn:
        summary_rows = []
        for tbl in tables:
            try:
                res = conn.execute(text(f"SELECT COUNT(*) FROM {tbl};")).scalar()
                summary_rows.append({"Table Name": tbl, "Record Count": f"{res:,}"})
            except Exception as e:
                summary_rows.append({"Table Name": tbl, "Record Count": f"Error: {e}"})

        df_summary = pd.DataFrame(summary_rows)
        print(df_summary.to_string(index=False))

        print("\n" + "-" * 65)
        print("SAMPLE PRODUCTS (Top 5):")
        print("-" * 65)
        sample_prods = pd.read_sql("SELECT product_id, sku, product_name, category, unit_price, unit_cost FROM products LIMIT 5;", conn)
        print(sample_prods.to_string(index=False))

        print("\n" + "-" * 65)
        print("SAMPLE SUPPLIERS:")
        print("-" * 65)
        sample_sups = pd.read_sql("SELECT supplier_id, supplier_name, lead_time_days, reliability_score, defect_rate, ordering_cost FROM suppliers;", conn)
        print(sample_sups.to_string(index=False))

        print("\n" + "-" * 65)
        print("SAMPLE PURCHASE ORDERS (Top 5):")
        print("-" * 65)
        sample_pos = pd.read_sql("SELECT po_id, supplier_id, product_id, order_date, expected_delivery_date, status, quantity_ordered, defect_count, is_on_time FROM purchase_orders LIMIT 5;", conn)
        print(sample_pos.to_string(index=False))

        print("\n" + "-" * 65)
        print("SAMPLE INVENTORY SNAPSHOT (Top 5):")
        print("-" * 65)
        sample_inv = pd.read_sql("SELECT product_id, current_stock, reserved_stock, reorder_point, safety_stock FROM inventory LIMIT 5;", conn)
        print(sample_inv.to_string(index=False))
        print("=" * 65 + "\n")


def main():
    parser = argparse.ArgumentParser(description="SupplyChainIQ Phase 1: Data Pipeline & PostgreSQL Schema Ingestion")
    parser.add_argument("--raw-csv", type=str, default=str(RAW_DATA_PATH), help="Path to input raw sales CSV file")
    parser.add_argument("--db-url", type=str, default=DATABASE_URL, help="Database connection URL")
    parser.add_argument("--generate-new-sample", action="store_true", help="Force regenerate sample raw CSV before ingestion")
    args = parser.parse_args()

    if args.generate_new_sample:
        from sample_data.generate_raw_sample import generate_raw_retail_csv
        generate_raw_retail_csv(output_path=args.raw_csv)

    pipeline = DataIngestionPipeline(raw_csv_path=args.raw_csv, db_url=args.db_url)
    pipeline.run()

    engine = get_engine(args.db_url)
    display_database_summary(engine)


if __name__ == "__main__":
    main()
