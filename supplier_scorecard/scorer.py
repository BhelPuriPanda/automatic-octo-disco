from typing import Dict
import pandas as pd
import numpy as np


class SupplierScorer:
    """
    Evaluates Supplier Performance using the standard 4-Pillar Supply Chain Composite Model:
    - 40% OTIF (On-Time & In-Full fulfillment)
    - 30% Lead Time Adherence & Reliability
    - 20% Quality & Defect Rate (PPM / Defect %)
    - 10% Cost Competitiveness & Price Index
    """

    WEIGHT_OTIF = 0.40
    WEIGHT_LEAD_TIME = 0.30
    WEIGHT_QUALITY = 0.20
    WEIGHT_COST = 0.10

    @classmethod
    def calculate_score(
        cls,
        total_orders: int,
        on_time_in_full_orders: int,
        on_time_orders: int,
        avg_delay_days: float,
        lead_time_std: float,
        total_received_qty: int,
        total_defect_qty: int,
        cost_ratio: float = 1.0
    ) -> Dict[str, float]:
        if total_orders == 0:
            return {
                "otif_rate_pct": 100.0,
                "otif_score": 100.0,
                "lead_time_score": 100.0,
                "quality_score": 100.0,
                "cost_score": 100.0,
                "composite_score": 100.0,
                "tier": "Tier 1 (Platinum)",
                "risk_level": "Low Risk"
            }

        # 1. OTIF Score (40% Weight)
        otif_rate = (on_time_in_full_orders / total_orders) * 100.0
        otif_score = max(0.0, min(otif_rate, 100.0))

        # 2. Lead Time Score (30% Weight)
        # Penalize delivery delays and lead time volatility
        on_time_rate = (on_time_orders / total_orders) * 100.0
        lt_penalty = (max(avg_delay_days, 0.0) * 10.0) + (lead_time_std * 3.0)
        lead_time_score = max(0.0, min(on_time_rate - lt_penalty, 100.0))

        # 3. Quality Score (20% Weight)
        defect_rate_pct = (total_defect_qty / max(total_received_qty, 1)) * 100.0
        # 0% defect = 100 pts; each 1% defect deducts 25 pts (4% defect -> 0 pts)
        quality_score = max(0.0, min(100.0 - (defect_rate_pct * 25.0), 100.0))

        # 4. Cost Competitiveness Score (10% Weight)
        # cost_ratio = supplier_cost / market_baseline_cost
        if cost_ratio <= 1.0:
            cost_score = min(100.0 + (1.0 - cost_ratio) * 50.0, 100.0)
        else:
            cost_score = max(0.0, 100.0 - (cost_ratio - 1.0) * 100.0)

        # Composite Weighted Score
        composite = (
            (cls.WEIGHT_OTIF * otif_score) +
            (cls.WEIGHT_LEAD_TIME * lead_time_score) +
            (cls.WEIGHT_QUALITY * quality_score) +
            (cls.WEIGHT_COST * cost_score)
        )
        composite = round(max(0.0, min(composite, 100.0)), 2)

        # Tier & Risk Classification
        if composite >= 90.0:
            tier = "Tier 1 (Platinum)"
            risk = "Low Risk / Preferred"
        elif composite >= 80.0:
            tier = "Tier 2 (Gold)"
            risk = "Moderate Risk / Standard"
        elif composite >= 65.0:
            tier = "Tier 3 (Silver)"
            risk = "Elevated Risk / Action Plan Required"
        else:
            tier = "Tier 4 (At Risk)"
            risk = "High Risk / Review Alternate Sourcing"

        return {
            "otif_rate_pct": round(otif_rate, 2),
            "otif_score": round(otif_score, 2),
            "lead_time_score": round(lead_time_score, 2),
            "defect_rate_pct": round(defect_rate_pct, 3),
            "quality_score": round(quality_score, 2),
            "cost_score": round(cost_score, 2),
            "composite_score": composite,
            "tier": tier,
            "risk_level": risk
        }
