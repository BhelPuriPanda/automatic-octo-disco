from typing import Dict, List, Tuple
import pandas as pd
import numpy as np


class ABCAnalyzer:
    """
    Performs Pareto ABC and ABC-XYZ Multi-Dimensional Inventory Classification:
    
    1. ABC Analysis (By Annual Value / Revenue Contribution):
       - Class A: Top ~80% of total revenue/value (High-value items, tight control)
       - Class B: Next ~15% of total value (80% - 95% cumulative, moderate control)
       - Class C: Bottom ~5% of total value (95% - 100% cumulative, bulk control)
       
    2. XYZ Analysis (By Demand Predictability / Volatility):
       - Coefficient of Variation CV = standard_deviation / mean
       - Class X: CV < 0.50 (Constant, highly predictable demand)
       - Class Y: 0.50 <= CV < 1.00 (Moderate variability / seasonality)
       - Class Z: CV >= 1.00 (Erratic, lumpy, intermittent demand)
    """

    @staticmethod
    def classify_abc(df: pd.DataFrame, value_col: str = "annual_revenue") -> pd.DataFrame:
        df = df.copy()
        if df.empty or value_col not in df.columns:
            df["abc_class"] = "C"
            df["cumulative_value_pct"] = 100.0
            return df

        # Sort descending by annual value
        df = df.sort_values(by=value_col, ascending=False).reset_index(drop=True)
        total_val = df[value_col].sum()
        if total_val <= 0:
            df["abc_class"] = "C"
            df["cumulative_value_pct"] = 100.0
            return df

        df["value_share_pct"] = (df[value_col] / total_val) * 100.0
        df["cumulative_value_pct"] = df["value_share_pct"].cumsum()

        def assign_abc(cum_pct):
            if cum_pct <= 70.0:
                return "A"
            elif cum_pct <= 90.0:
                return "B"
            else:
                return "C"

        df["abc_class"] = df["cumulative_value_pct"].apply(assign_abc)
        return df

    @staticmethod
    def classify_xyz(df: pd.DataFrame, mean_col: str = "daily_avg_demand", std_col: str = "daily_demand_std") -> pd.DataFrame:
        df = df.copy()
        
        def calculate_cv(row):
            mean = row.get(mean_col, 0.0)
            std = row.get(std_col, 0.0)
            if mean <= 0:
                return 999.0
            return std / mean

        df["cv_demand"] = df.apply(calculate_cv, axis=1)

        def assign_xyz(cv):
            if cv < 0.60:
                return "X"
            elif cv < 1.10:
                return "Y"
            else:
                return "Z"

        df["xyz_class"] = df["cv_demand"].apply(assign_xyz)
        df["abc_xyz_segment"] = df["abc_class"] + df["xyz_class"]
        return df
