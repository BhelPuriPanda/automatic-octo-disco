"""
SupplyChainIQ - Phase 5 Runner Script: Supplier Performance Scorecard & Risk Profiling
Calculates the 4-Pillar Composite Supplier Score (40% OTIF + 30% Lead Time + 20% Quality + 10% Cost),
ranks vendor strategic tiers, and updates the 'suppliers' database table.
"""

import argparse
import sys
import pandas as pd
from sqlalchemy import text
from config import DATABASE_URL
from database.connection import get_engine
from supplier_scorecard.engine import SupplierScorecardEngine


def display_supplier_db_verification(engine):
    print("\n" + "=" * 90)
    print("      DATABASE VERIFICATION: UPDATED SUPPLIERS TABLE (RELIABILITY & DEFECTS)   ")
    print("=" * 90)
    with engine.connect() as conn:
        df = pd.read_sql("""
            SELECT supplier_id, supplier_name, lead_time_days,
                   reliability_score, defect_rate, ordering_cost
            FROM suppliers
            ORDER BY reliability_score DESC;
        """, conn)
        print(df.to_string(index=False))
    print("=" * 90 + "\n")


def main():
    parser = argparse.ArgumentParser(description="SupplyChainIQ Phase 5: Supplier Performance Scorecard")
    parser.add_argument("--db-url", type=str, default=DATABASE_URL, help="Database connection URL")
    args = parser.parse_args()

    print("\n" + "=" * 90)
    print("      SUPPLYCHAINIQ - PHASE 5: SUPPLIER PERFORMANCE SCORECARD & RISK MATRIX    ")
    print("      Weights: 40% OTIF | 30% Lead Time Adherence | 20% Quality | 10% Cost     ")
    print("=" * 90)

    engine_runner = SupplierScorecardEngine(db_url=args.db_url)
    scorecard_df = engine_runner.generate_scorecard()

    # 1. Executive Scorecard Table
    print("\n" + "-" * 90)
    print("SUPPLIER EXECUTIVE SCORECARD & 4-PILLAR WEIGHTED SCORES:")
    print("-" * 90)
    exec_cols = [
        "supplier_id", "supplier_name", "otif_score (40%)", "lead_time_score (30%)",
        "quality_score (20%)", "cost_score (10%)", "composite_score", "tier", "risk_level"
    ]
    print(scorecard_df[exec_cols].to_string(index=False))

    # 2. Operational Delivery & Quality Metrics Table
    print("\n" + "-" * 90)
    print("OPERATIONAL FULFILLMENT, LEAD TIME & QUALITY DEFECT BREAKDOWN:")
    print("-" * 90)
    ops_cols = [
        "supplier_id", "supplier_name", "total_pos_delivered", "otif_rate",
        "actual_avg_lead_time", "avg_delay_days", "defect_rate"
    ]
    print(scorecard_df[ops_cols].to_string(index=False))

    # 3. Database Verification
    db_engine = get_engine(args.db_url)
    display_supplier_db_verification(db_engine)
    db_engine.dispose()


if __name__ == "__main__":
    main()
