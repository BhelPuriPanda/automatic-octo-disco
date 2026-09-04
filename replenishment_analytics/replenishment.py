import logging
import datetime
import math
from typing import Dict, List, Optional
import pandas as pd
import numpy as np
from sqlalchemy import text

from config import DATABASE_URL
from database.connection import get_engine
from database.models import Product, Inventory, Supplier, SupplierProduct, InventoryMetric
from replenishment_analytics.abc_analysis import ABCAnalyzer
from replenishment_analytics.risk_engine import StockoutRiskEngine

logger = logging.getLogger("SupplyChainIQ.Replenishment")


class ReplenishmentPlanner:
    """
    End-to-End Replenishment & ABC Risk Analytics Planner:
    1. Extracts full product, inventory, supplier, and sales metrics
    2. Runs Pareto ABC + XYZ classification
    3. Computes Stockout Risk Score (0-100), Days of Supply (DOS), and Turnover Ratio
    4. Generates automated purchase order recommendations with MOQ compliance
    5. Persists calculated analytics back into 'inventory_metrics' table
    """

    def __init__(self, db_url: Optional[str] = None):
        self.db_url = db_url or DATABASE_URL
        self.engine = get_engine(self.db_url)

    def extract_inventory_state(self) -> pd.DataFrame:
        query = """
            SELECT p.product_id, p.sku, p.product_name, p.category, p.unit_price, p.unit_cost,
                   i.current_stock, i.reserved_stock, i.safety_stock, i.reorder_point, i.max_stock,
                   im.annual_demand, im.daily_avg_demand, im.demand_std_dev, im.economic_order_qty,
                   COALESCE(sp.lead_time_days, s.lead_time_days, 7) as lead_time_days,
                   COALESCE(sp.min_order_qty, 10) as min_order_qty,
                   COALESCE(sp.unit_cost, p.unit_cost) as supplier_unit_cost,
                   s.supplier_id, s.supplier_name
            FROM products p
            JOIN inventory i ON p.product_id = i.product_id
            LEFT JOIN inventory_metrics im ON p.product_id = im.product_id
            LEFT JOIN supplier_products sp ON p.product_id = sp.product_id
            LEFT JOIN suppliers s ON sp.supplier_id = s.supplier_id
            GROUP BY p.product_id;
        """
        with self.engine.connect() as conn:
            df = pd.read_sql(query, conn)

        # Calculate annual revenue contribution for ABC classification
        df["annual_revenue"] = df["annual_demand"] * df["unit_price"]
        return df

    def run_plan(self) -> Dict[str, pd.DataFrame]:
        logger.info("Executing Phase 4 ABC analysis, stockout risk scoring, and replenishment planning...")
        df = self.extract_inventory_state()

        if df.empty:
            raise ValueError("No inventory/product records found. Ensure Phase 1 and Phase 3 have run.")

        # 1. ABC & XYZ Classification
        abc_df = ABCAnalyzer.classify_abc(df, value_col="annual_revenue")
        abc_xyz_df = ABCAnalyzer.classify_xyz(abc_df, mean_col="daily_avg_demand", std_col="demand_std_dev")

        # 2. Stockout Risk & DOS Scoring
        full_metrics_df = StockoutRiskEngine.calculate_metrics(abc_xyz_df)

        # 3. Generate Replenishment Recommendations
        recommendations = []
        for _, row in full_metrics_df.iterrows():
            available = row["available_stock"]
            rop = row["reorder_point"]
            ss = row["safety_stock"]
            eoq = row["economic_order_qty"]
            max_s = row["max_stock"]
            moq = row["min_order_qty"]
            sup_cost = row["supplier_unit_cost"]

            # Trigger condition: Available stock <= ROP
            if available <= rop:
                urgency = "CRITICAL (BELOW SS)" if available < ss else "STANDARD REPLENISHMENT"
                
                # Order Quantity: at least EOQ, bringing stock up to Max Stock, complying with MOQ
                raw_qty = max(eoq, max_s - available)
                # Round up to MOQ multiple
                order_qty = int(math.ceil(raw_qty / moq) * moq)
                total_cost = round(order_qty * sup_cost, 2)

                recommendations.append({
                    "product_id": row["product_id"],
                    "sku": row["sku"],
                    "product_name": row["product_name"],
                    "category": row["category"],
                    "abc_class": row["abc_class"],
                    "current_stock": row["current_stock"],
                    "reorder_point": rop,
                    "safety_stock": ss,
                    "recommended_reorder_qty": order_qty,
                    "moq": moq,
                    "supplier_id": row["supplier_id"],
                    "supplier_name": row["supplier_name"],
                    "lead_time_days": row["lead_time_days"],
                    "supplier_unit_cost": sup_cost,
                    "estimated_order_cost": total_cost,
                    "urgency": urgency
                })
            else:
                # Stock is healthy; recommended qty = 0
                pass

        recom_df = pd.DataFrame(recommendations)
        if recom_df.empty:
            recom_df = pd.DataFrame(columns=[
                "product_id", "sku", "product_name", "category", "abc_class",
                "current_stock", "reorder_point", "safety_stock",
                "recommended_reorder_qty", "supplier_name", "estimated_order_cost", "urgency"
            ])

        # 4. Update database 'inventory_metrics'
        self._update_inventory_metrics(full_metrics_df, recom_df)

        self.engine.dispose()
        return {
            "full_metrics": full_metrics_df,
            "replenishment_orders": recom_df
        }

    def _update_inventory_metrics(self, metrics_df: pd.DataFrame, recom_df: pd.DataFrame):
        recom_map = dict(zip(recom_df["product_id"], recom_df["recommended_reorder_qty"])) if not recom_df.empty else {}

        with self.engine.begin() as conn:
            for _, row in metrics_df.iterrows():
                pid = row["product_id"]
                recom_qty = recom_map.get(pid, 0.0)

                conn.execute(
                    text("""
                        UPDATE inventory_metrics
                        SET abc_classification = :abc,
                            stockout_risk_score = :risk,
                            turnover_ratio = :turnover,
                            recommended_reorder_qty = :recom_qty
                        WHERE product_id = :pid;
                    """),
                    {
                        "abc": row["abc_class"],
                        "risk": float(row["stockout_risk_score"]),
                        "turnover": float(row["inventory_turnover"]),
                        "recom_qty": float(recom_qty),
                        "pid": pid
                    }
                )

        logger.info(f"Updated inventory_metrics for {len(metrics_df)} products with ABC classes, risk scores, and replenishment recommendations.")
