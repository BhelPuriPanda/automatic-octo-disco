import math
import logging
import datetime
from typing import Dict, List, Optional
import pandas as pd
import numpy as np
from sqlalchemy import text
from sqlalchemy.orm import Session

from config import DATABASE_URL
from database.connection import get_engine, get_session
from database.models import Product, Inventory, Supplier, SupplierProduct, PurchaseOrder, InventoryMetric
from inventory_optimization.formulas import InventoryFormulas

logger = logging.getLogger("SupplyChainIQ.InventoryOptimization")


class InventoryOptimizer:
    """
    Multi-Echelon Inventory Optimization Engine:
    - Calculates demand mean & standard deviation per SKU
    - Evaluates lead time and supplier ordering parameters ($L$, $S$, $\sigma_L$)
    - Computes Safety Stock (SS) across target service levels (CSL)
    - Computes Reorder Point (ROP = DDLT + SS)
    - Computes Economic Order Quantity (EOQ) and Total Annual Inventory Cost (TIC)
    - Updates 'inventory' and 'inventory_metrics' tables in PostgreSQL / SQLite
    """

    def __init__(self, db_url: Optional[str] = None, default_service_level: float = 0.95):
        self.db_url = db_url or DATABASE_URL
        self.service_level = default_service_level
        self.engine = get_engine(self.db_url)

    def optimize_all_products(self) -> pd.DataFrame:
        logger.info(f"Starting inventory optimization with target Service Level = {self.service_level*100:.1f}% (Z={InventoryFormulas.get_z_score(self.service_level):.3f})...")

        with self.engine.connect() as conn:
            # 1. Fetch products & primary supplier mapping
            prods_query = """
                SELECT p.product_id, p.sku, p.product_name, p.category, p.unit_price, p.unit_cost, p.holding_cost_rate,
                       COALESCE(sp.lead_time_days, s.lead_time_days, 7) as lead_time_days,
                       COALESCE(s.ordering_cost, 50.0) as ordering_cost,
                       s.supplier_id, s.supplier_name
                FROM products p
                LEFT JOIN supplier_products sp ON p.product_id = sp.product_id
                LEFT JOIN suppliers s ON sp.supplier_id = s.supplier_id
                GROUP BY p.product_id;
            """
            products_df = pd.read_sql(prods_query, conn)

            # 2. Fetch daily sales aggregation per product
            sales_query = """
                SELECT product_id, DATE(sale_date) as sale_date, SUM(quantity) as daily_qty
                FROM sales
                GROUP BY product_id, DATE(sale_date);
            """
            sales_df = pd.read_sql(sales_query, conn)

            # 3. Fetch purchase order lead time variances if available
            po_query = """
                SELECT product_id,
                       CAST((JULIANDAY(actual_delivery_date) - JULIANDAY(order_date)) as REAL) as actual_lt
                FROM purchase_orders
                WHERE actual_delivery_date IS NOT NULL;
            """
            try:
                po_df = pd.read_sql(po_query, conn)
            except Exception:
                # Fallback for PostgreSQL syntax if running on Postgres
                po_query_pg = """
                    SELECT product_id,
                           EXTRACT(DAY FROM (actual_delivery_date - order_date)) as actual_lt
                    FROM purchase_orders
                    WHERE actual_delivery_date IS NOT NULL;
                """
                po_df = pd.read_sql(po_query_pg, conn)

        # Date range for continuous timeline
        sales_df["sale_date"] = pd.to_datetime(sales_df["sale_date"])
        min_date = sales_df["sale_date"].min()
        max_date = sales_df["sale_date"].max()
        full_days = max((max_date - min_date).days + 1, 1)
        full_date_idx = pd.date_range(start=min_date, end=max_date, freq="D")

        optimization_results = []
        now_utc = datetime.datetime.now(datetime.timezone.utc)

        for _, prod in products_df.iterrows():
            prod_id = prod["product_id"]
            sku = prod["sku"]
            prod_name = prod["product_name"]
            unit_cost = float(prod["unit_cost"])
            unit_price = float(prod["unit_price"])
            holding_cost_rate = float(prod["holding_cost_rate"])
            nominal_lt = float(prod["lead_time_days"])
            ordering_cost_s = float(prod["ordering_cost"])

            # Continuous daily demand
            prod_sales = sales_df[sales_df["product_id"] == prod_id]
            if not prod_sales.empty:
                s_indexed = prod_sales.set_index("sale_date")["daily_qty"].reindex(full_date_idx, fill_value=0)
                daily_mean = float(s_indexed.mean())
                daily_std = float(s_indexed.std(ddof=1)) if len(s_indexed) > 1 else 1.0
                annual_demand = daily_mean * 365.0
            else:
                daily_mean = 1.0
                daily_std = 0.5
                annual_demand = 365.0

            # Lead time standard deviation from PO history
            prod_pos = po_df[po_df["product_id"] == prod_id] if not po_df.empty else pd.DataFrame()
            if len(prod_pos) >= 3:
                lt_std = float(prod_pos["actual_lt"].std(ddof=1))
            else:
                lt_std = 1.0  # default 1 day lead time buffer

            # -------------------------------------------------------------
            # INVENTORY OPTIMIZATION CALCULATIONS
            # -------------------------------------------------------------
            # 1. Safety Stock
            safety_stock = InventoryFormulas.calculate_safety_stock(
                daily_demand_std=daily_std,
                lead_time_days=nominal_lt,
                service_level=self.service_level,
                lead_time_std=lt_std,
                daily_demand_mean=daily_mean
            )

            # 2. Demand During Lead Time & Reorder Point
            ddlt = daily_mean * nominal_lt
            rop = InventoryFormulas.calculate_reorder_point(
                daily_demand_mean=daily_mean,
                lead_time_days=nominal_lt,
                safety_stock=safety_stock
            )

            # 3. Economic Order Quantity & Cost Model
            eoq_metrics = InventoryFormulas.calculate_eoq(
                annual_demand=annual_demand,
                ordering_cost_s=ordering_cost_s,
                unit_cost=unit_cost,
                holding_cost_rate_h=holding_cost_rate
            )
            eoq = eoq_metrics["eoq"]
            max_stock = round(rop + eoq, 2)

            optimization_results.append({
                "product_id": prod_id,
                "sku": sku,
                "product_name": prod_name,
                "unit_cost": unit_cost,
                "daily_avg_demand": round(daily_mean, 2),
                "daily_demand_std": round(daily_std, 2),
                "annual_demand": round(annual_demand, 1),
                "lead_time_days": nominal_lt,
                "safety_stock": int(math.ceil(safety_stock)),
                "ddlt": round(ddlt, 2),
                "reorder_point": int(math.ceil(rop)),
                "economic_order_qty": int(math.ceil(eoq)),
                "max_stock": int(math.ceil(max_stock)),
                "annual_ordering_cost": eoq_metrics["annual_ordering_cost"],
                "annual_holding_cost": eoq_metrics["annual_holding_cost"],
                "total_annual_cost": eoq_metrics["total_annual_inventory_cost"],
                "orders_per_year": eoq_metrics["orders_per_year"],
                "cycle_time_days": eoq_metrics["cycle_time_days"]
            })

        results_df = pd.DataFrame(optimization_results)

        # -------------------------------------------------------------
        # DATABASE PERSISTENCE
        # -------------------------------------------------------------
        self._persist_to_db(results_df, now_utc)
        self.engine.dispose()
        return results_df

    def _persist_to_db(self, results_df: pd.DataFrame, timestamp: datetime.datetime):
        with self.engine.begin() as conn:
            # 1. Update inventory table with optimized ROP, SS, and Max Stock
            for _, row in results_df.iterrows():
                conn.execute(
                    text("""
                        UPDATE inventory
                        SET reorder_point = :rop,
                            safety_stock = :ss,
                            max_stock = :max_s,
                            last_updated = :ts
                        WHERE product_id = :pid;
                    """),
                    {
                        "rop": int(row["reorder_point"]),
                        "ss": int(row["safety_stock"]),
                        "max_s": int(row["max_stock"]),
                        "ts": timestamp,
                        "pid": row["product_id"]
                    }
                )

            # 2. Populate inventory_metrics table
            metrics_records = []
            for _, row in results_df.iterrows():
                metrics_records.append({
                    "product_id": row["product_id"],
                    "calculation_date": timestamp,
                    "annual_demand": row["annual_demand"],
                    "daily_avg_demand": row["daily_avg_demand"],
                    "demand_std_dev": row["daily_demand_std"],
                    "lead_time_days": row["lead_time_days"],
                    "safety_stock": float(row["safety_stock"]),
                    "reorder_point": float(row["reorder_point"]),
                    "economic_order_qty": float(row["economic_order_qty"]),
                    "stockout_risk_score": None,
                    "abc_classification": None,
                    "turnover_ratio": None,
                    "recommended_reorder_qty": None
                })

            # Clear and populate latest metrics snapshot
            conn.execute(text("DELETE FROM inventory_metrics;"))
            pd.DataFrame(metrics_records).to_sql("inventory_metrics", con=conn, if_exists="append", index=False)

        logger.info(f"Updated inventory policies and persisted {len(results_df)} metrics records to database.")
