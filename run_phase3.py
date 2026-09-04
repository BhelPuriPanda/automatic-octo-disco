"""
SupplyChainIQ - Phase 3 Runner Script: Multi-Echelon Inventory Optimization Engine
Calculates Safety Stock (SS), Reorder Point (ROP), Economic Order Quantity (EOQ),
and Total Inventory Cost (TIC) across configurable Service Levels (CSL),
and updates 'inventory' and 'inventory_metrics' database tables.
"""

import argparse
import sys
import pandas as pd
from sqlalchemy import text
from config import DATABASE_URL
from database.connection import get_engine
from inventory_optimization.optimizer import InventoryOptimizer
from inventory_optimization.formulas import InventoryFormulas


def display_inventory_verification(engine):
    print("\n" + "=" * 80)
    print("      DATABASE VERIFICATION: UPDATED INVENTORY & METRICS TABLES        ")
    print("=" * 80)

    with engine.connect() as conn:
        print("-" * 80)
        print("UPDATED INVENTORY TABLE (Top 6 SKUs):")
        print("-" * 80)
        inv_df = pd.read_sql("""
            SELECT i.product_id, p.sku, p.product_name,
                   i.current_stock, i.safety_stock, i.reorder_point, i.max_stock,
                   CASE WHEN i.current_stock <= i.reorder_point THEN 'REORDER NEEDED' ELSE 'HEALTHY' END as stock_status
            FROM inventory i
            JOIN products p ON i.product_id = p.product_id
            LIMIT 6;
        """, conn)
        print(inv_df.to_string(index=False))

        print("\n" + "-" * 80)
        print("INVENTORY_METRICS TABLE SNAPSHOT (Top 6 SKUs):")
        print("-" * 80)
        metrics_df = pd.read_sql("""
            SELECT product_id, annual_demand, daily_avg_demand, demand_std_dev,
                   lead_time_days, safety_stock, reorder_point, economic_order_qty
            FROM inventory_metrics
            LIMIT 6;
        """, conn)
        print(metrics_df.to_string(index=False))
        print("=" * 80 + "\n")


def main():
    parser = argparse.ArgumentParser(description="SupplyChainIQ Phase 3: Inventory Math & Optimization Policies")
    parser.add_argument("--db-url", type=str, default=DATABASE_URL, help="Database connection URL")
    parser.add_argument("--service-level", type=float, default=0.95, help="Target Cycle Service Level (e.g. 0.90, 0.95, 0.98, 0.99)")
    args = parser.parse_args()

    z_val = InventoryFormulas.get_z_score(args.service_level)
    print("\n" + "=" * 80)
    print("    SUPPLYCHAINIQ - PHASE 3: INVENTORY POLICY & EOQ OPTIMIZATION       ")
    print(f"    Target Cycle Service Level: {args.service_level*100:.1f}% | Normal Z-Score: {z_val:.3f}")
    print("=" * 80)

    optimizer = InventoryOptimizer(db_url=args.db_url, default_service_level=args.service_level)
    results_df = optimizer.optimize_all_products()

    # Formatted display of policy table
    policy_cols = [
        "product_id", "sku", "lead_time_days", "daily_avg_demand",
        "daily_demand_std", "safety_stock", "reorder_point",
        "economic_order_qty", "max_stock"
    ]
    print("\n" + "-" * 80)
    print("OPTIMIZED INVENTORY POLICIES (Safety Stock, ROP, EOQ):")
    print("-" * 80)
    print(results_df[policy_cols].to_string(index=False))

    # Formatted display of financial breakdown
    cost_cols = [
        "product_id", "unit_cost", "annual_demand", "orders_per_year",
        "cycle_time_days", "annual_ordering_cost", "annual_holding_cost",
        "total_annual_cost"
    ]
    print("\n" + "-" * 80)
    print("ANNUAL INVENTORY FINANCIAL BREAKDOWN (TIC = Ordering Cost + Holding Cost):")
    print("-" * 80)
    print(results_df[cost_cols].to_string(index=False))

    # Database verification
    db_engine = get_engine(args.db_url)
    display_inventory_verification(db_engine)
    db_engine.dispose()


if __name__ == "__main__":
    main()
