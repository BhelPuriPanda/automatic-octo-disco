import logging
import datetime
from typing import Dict, List, Optional
import pandas as pd
import numpy as np
from sqlalchemy import text

from config import DATABASE_URL
from database.connection import get_engine
from database.models import Supplier, PurchaseOrder, Product
from supplier_scorecard.scorer import SupplierScorer

logger = logging.getLogger("SupplyChainIQ.SupplierScorecard")


class SupplierScorecardEngine:
    """
    Executes historical supplier scorecard audits across all suppliers:
    - Extracts PO delivery records, OTIF timestamps, and quality defect counts
    - Computes 4-pillar composite scoring
    - Ranks suppliers by strategic tier and operational risk
    - Persists updated reliability scores back into the 'suppliers' table
    """

    def __init__(self, db_url: Optional[str] = None):
        self.db_url = db_url or DATABASE_URL
        self.engine = get_engine(self.db_url)

    def extract_po_history(self) -> pd.DataFrame:
        query = """
            SELECT po.po_id, po.supplier_id, s.supplier_name, s.lead_time_days as promised_lt,
                   s.ordering_cost, po.product_id, p.unit_cost as benchmark_cost,
                   po.unit_cost as po_unit_cost, po.order_date, po.expected_delivery_date,
                   po.actual_delivery_date, po.quantity_ordered, po.quantity_received,
                   po.defect_count, po.status, po.is_on_time, po.is_in_full
            FROM purchase_orders po
            JOIN suppliers s ON po.supplier_id = s.supplier_id
            JOIN products p ON po.product_id = p.product_id
            WHERE po.status = 'Delivered' AND po.actual_delivery_date IS NOT NULL;
        """
        with self.engine.connect() as conn:
            df = pd.read_sql(query, conn)
        return df

    def generate_scorecard(self) -> pd.DataFrame:
        logger.info("Generating supplier performance scorecards from historical purchase orders...")
        df = self.extract_po_history()

        with self.engine.connect() as conn:
            all_suppliers = pd.read_sql("SELECT supplier_id, supplier_name, lead_time_days, ordering_cost FROM suppliers;", conn)

        if df.empty:
            logger.warning("No delivered purchase orders found for scoring. Returning baseline supplier records.")
            return all_suppliers

        # Convert date columns
        df["order_date"] = pd.to_datetime(df["order_date"])
        df["expected_delivery_date"] = pd.to_datetime(df["expected_delivery_date"])
        df["actual_delivery_date"] = pd.to_datetime(df["actual_delivery_date"])

        # Delay in days: actual - expected
        df["delay_days"] = (df["actual_delivery_date"] - df["expected_delivery_date"]).dt.total_seconds() / 86400.0
        df["actual_lt_days"] = (df["actual_delivery_date"] - df["order_date"]).dt.total_seconds() / 86400.0

        scorecard_rows = []

        for _, sup in all_suppliers.iterrows():
            sup_id = sup["supplier_id"]
            sup_name = sup["supplier_name"]
            promised_lt = sup["lead_time_days"]
            ord_cost = sup["ordering_cost"]

            sup_pos = df[df["supplier_id"] == sup_id]

            if sup_pos.empty:
                scorecard_rows.append({
                    "supplier_id": sup_id,
                    "supplier_name": sup_name,
                    "total_pos_delivered": 0,
                    "otif_rate": "100.0%",
                    "avg_delay_days": 0.0,
                    "actual_avg_lead_time": promised_lt,
                    "defect_rate": "0.0%",
                    "otif_score (40%)": 100.0,
                    "lead_time_score (30%)": 100.0,
                    "quality_score (20%)": 100.0,
                    "cost_score (10%)": 100.0,
                    "composite_score": 100.0,
                    "tier": "Tier 1 (Platinum)",
                    "risk_level": "Low Risk / Preferred"
                })
                continue

            total_orders = len(sup_pos)
            # is_on_time and is_in_full (handles bool or int 1/0)
            on_time_mask = (sup_pos["is_on_time"] == True) | (sup_pos["is_on_time"] == 1)
            in_full_mask = (sup_pos["is_in_full"] == True) | (sup_pos["is_in_full"] == 1)
            otif_mask = on_time_mask & in_full_mask

            on_time_orders = int(on_time_mask.sum())
            otif_orders = int(otif_mask.sum())

            avg_delay = float(sup_pos["delay_days"].mean())
            actual_avg_lt = float(sup_pos["actual_lt_days"].mean())
            lt_std = float(sup_pos["actual_lt_days"].std(ddof=1)) if total_orders > 1 else 1.0

            total_received = int(sup_pos["quantity_received"].sum())
            total_defects = int(sup_pos["defect_count"].sum())

            # Cost competitiveness ratio
            cost_ratio = float((sup_pos["po_unit_cost"] / sup_pos["benchmark_cost"]).mean())

            scores = SupplierScorer.calculate_score(
                total_orders=total_orders,
                on_time_in_full_orders=otif_orders,
                on_time_orders=on_time_orders,
                avg_delay_days=avg_delay,
                lead_time_std=lt_std,
                total_received_qty=total_received,
                total_defect_qty=total_defects,
                cost_ratio=cost_ratio
            )

            scorecard_rows.append({
                "supplier_id": sup_id,
                "supplier_name": sup_name,
                "total_pos_delivered": total_orders,
                "otif_rate": f"{scores['otif_rate_pct']:.1f}%",
                "avg_delay_days": round(avg_delay, 1),
                "actual_avg_lead_time": round(actual_avg_lt, 1),
                "defect_rate": f"{scores['defect_rate_pct']:.2f}%",
                "otif_score (40%)": scores["otif_score"],
                "lead_time_score (30%)": scores["lead_time_score"],
                "quality_score (20%)": scores["quality_score"],
                "cost_score (10%)": scores["cost_score"],
                "composite_score": scores["composite_score"],
                "tier": scores["tier"],
                "risk_level": scores["risk_level"],
                "_raw_composite": scores["composite_score"],
                "_raw_defect_rate": scores["defect_rate_pct"] / 100.0
            })

        scorecard_df = pd.DataFrame(scorecard_rows).sort_values(by="_raw_composite", ascending=False).reset_index(drop=True)

        # Update database suppliers table
        self._update_supplier_records(scorecard_df)
        self.engine.dispose()
        return scorecard_df

    def _update_supplier_records(self, scorecard_df: pd.DataFrame):
        with self.engine.begin() as conn:
            for _, row in scorecard_df.iterrows():
                conn.execute(
                    text("""
                        UPDATE suppliers
                        SET reliability_score = :rel,
                            defect_rate = :def_rate
                        WHERE supplier_id = :sid;
                    """),
                    {
                        "rel": round(float(row["_raw_composite"]) / 100.0, 3),
                        "def_rate": round(float(row["_raw_defect_rate"]), 4),
                        "sid": row["supplier_id"]
                    }
                )
        logger.info("Updated suppliers table with latest scorecard reliability and defect scores.")
