import pandas as pd
import numpy as np


class StockoutRiskEngine:
    """
    Evaluates inventory health, stockout risk index (0 - 100),
    Days of Supply (DOS), and Inventory Turnover Ratio per SKU.
    """

    @staticmethod
    def calculate_metrics(df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()

        def compute_row_risk(row):
            current = float(row.get("current_stock", 0))
            reserved = float(row.get("reserved_stock", 0))
            available = max(current - reserved, 0.0)
            daily_demand = float(row.get("daily_avg_demand", 1.0))
            ss = float(row.get("safety_stock", 0))
            rop = float(row.get("reorder_point", 0))
            max_s = float(row.get("max_stock", rop * 2.0))
            unit_cost = float(row.get("unit_cost", 1.0))
            annual_demand = float(row.get("annual_demand", daily_demand * 365.0))

            # 1. Days of Supply (DOS)
            dos = available / daily_demand if daily_demand > 0 else 999.0

            # 2. Stockout Risk Score (0 to 100)
            if available <= 0:
                risk_score = 100.0
                status = "CRITICAL STOCKOUT"
            elif available < ss:
                # Risk score between 75 and 99
                fraction = available / max(ss, 1.0)
                risk_score = 75.0 + (1.0 - fraction) * 24.0
                status = "HIGH RISK (BELOW SS)"
            elif available <= rop:
                # Risk score between 40 and 74
                span = max(rop - ss, 1.0)
                fraction = (available - ss) / span
                risk_score = 40.0 + (1.0 - fraction) * 34.0
                status = "REORDER NEEDED (BELOW ROP)"
            elif available > max_s * 1.5:
                # Overstock risk (capital tied up)
                risk_score = 5.0
                status = "OVERSTOCK RISK"
            else:
                # Healthy buffer
                span = max(max_s - rop, 1.0)
                fraction = min((available - rop) / span, 1.0)
                risk_score = max(5.0, 40.0 - (fraction * 35.0))
                status = "OPTIMAL BUFFER"

            # 3. Inventory Turnover Ratio = Annual COGS / Average Inventory Value
            annual_cogs = annual_demand * unit_cost
            avg_inv_units = max((current + ss) / 2.0, 1.0)
            avg_inv_val = avg_inv_units * unit_cost
            turnover = annual_cogs / avg_inv_val if avg_inv_val > 0 else 0.0

            return pd.Series({
                "available_stock": int(available),
                "days_of_supply": round(dos, 1),
                "stockout_risk_score": round(risk_score, 1),
                "stock_status": status,
                "inventory_turnover": round(turnover, 2)
            })

        risk_metrics = df.apply(compute_row_risk, axis=1)
        return pd.concat([df, risk_metrics], axis=1)
