"""
SupplyChainIQ - Phase 4 Runner Script: ABC Analysis, Stockout Risk & Replenishment Engine
Executes Pareto 80/15/5 ABC + XYZ classification, calculates Days of Supply (DOS),
evaluates 0-100 Stockout Risk Scores, generates automated replenishment POs with MOQ compliance,
and updates the 'inventory_metrics' database table.
"""

import argparse
import sys
import pandas as pd
from sqlalchemy import text
from config import DATABASE_URL
from database.connection import get_engine
from replenishment_analytics.replenishment import ReplenishmentPlanner


def display_metrics_verification(engine):
    print("\n" + "=" * 85)
    print("      DATABASE VERIFICATION: UPDATED INVENTORY_METRICS TABLE          ")
    print("=" * 85)
    with engine.connect() as conn:
        metrics_df = pd.read_sql("""
            SELECT im.product_id, p.sku, p.product_name,
                   im.abc_classification, im.stockout_risk_score,
                   im.turnover_ratio, im.recommended_reorder_qty
            FROM inventory_metrics im
            JOIN products p ON im.product_id = p.product_id
            ORDER BY im.stockout_risk_score DESC;
        """, conn)
        print(metrics_df.to_string(index=False))
    print("=" * 85 + "\n")


def main():
    parser = argparse.ArgumentParser(description="SupplyChainIQ Phase 4: ABC Analysis, Stockout Risk & Replenishment Planner")
    parser.add_argument("--db-url", type=str, default=DATABASE_URL, help="Database connection URL")
    args = parser.parse_args()

    print("\n" + "=" * 85)
    print("     SUPPLYCHAINIQ - PHASE 4: ABC ANALYSIS, RISK & REPLENISHMENT      ")
    print("=" * 85)

    planner = ReplenishmentPlanner(db_url=args.db_url)
    results = planner.run_plan()
    metrics_df = results["full_metrics"]
    recom_df = results["replenishment_orders"]

    # 1. ABC / XYZ Matrix Table
    print("\n" + "-" * 85)
    print("PARETO ABC & XYZ MULTI-DIMENSIONAL CLASSIFICATION:")
    print("-" * 85)
    abc_cols = [
        "product_id", "sku", "category", "annual_revenue",
        "value_share_pct", "cumulative_value_pct", "abc_class", "xyz_class", "abc_xyz_segment"
    ]
    formatted_abc = metrics_df[abc_cols].copy()
    formatted_abc["annual_revenue"] = formatted_abc["annual_revenue"].map(lambda x: f"${x:,.2f}")
    formatted_abc["value_share_pct"] = formatted_abc["value_share_pct"].map(lambda x: f"{x:.1f}%")
    formatted_abc["cumulative_value_pct"] = formatted_abc["cumulative_value_pct"].map(lambda x: f"{x:.1f}%")
    print(formatted_abc.to_string(index=False))

    # 2. Stock Health & Risk Scores Table
    print("\n" + "-" * 85)
    print("INVENTORY HEALTH, DAYS OF SUPPLY (DOS) & STOCKOUT RISK INDEX (0-100):")
    print("-" * 85)
    health_cols = [
        "product_id", "sku", "current_stock", "safety_stock", "reorder_point",
        "days_of_supply", "stockout_risk_score", "stock_status", "inventory_turnover"
    ]
    print(metrics_df[health_cols].to_string(index=False))

    # 3. Actionable Replenishment Recommendations Table
    print("\n" + "-" * 85)
    print("AUTOMATED REPLENISHMENT PURCHASE ORDER RECOMMENDATIONS:")
    print("-" * 85)
    if not recom_df.empty:
        recom_display_cols = [
            "product_id", "sku", "current_stock", "reorder_point",
            "recommended_reorder_qty", "supplier_name", "lead_time_days",
            "estimated_order_cost", "urgency"
        ]
        formatted_recom = recom_df[recom_display_cols].copy()
        formatted_recom["estimated_order_cost"] = formatted_recom["estimated_order_cost"].map(lambda x: f"${x:,.2f}")
        print(formatted_recom.to_string(index=False))
        total_reorder_cost = recom_df["estimated_order_cost"].sum()
        print(f"\n>>> Total Capital Required for Suggested Replenishment: ${total_reorder_cost:,.2f}")
    else:
        print("All SKU stock levels are currently above Reorder Point (ROP). No immediate purchase orders required.")

    # 4. Database Verification
    db_engine = get_engine(args.db_url)
    display_metrics_verification(db_engine)
    db_engine.dispose()


if __name__ == "__main__":
    main()
