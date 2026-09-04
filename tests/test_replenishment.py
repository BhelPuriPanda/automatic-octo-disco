import unittest
import tempfile
from pathlib import Path
import pandas as pd
import numpy as np

from replenishment_analytics.abc_analysis import ABCAnalyzer
from replenishment_analytics.risk_engine import StockoutRiskEngine
from replenishment_analytics.replenishment import ReplenishmentPlanner
from data_pipeline.ingest import DataIngestionPipeline
from inventory_optimization.optimizer import InventoryOptimizer
from sample_data.generate_raw_sample import generate_raw_retail_csv


class TestReplenishmentAnalytics(unittest.TestCase):

    def test_abc_classification(self):
        df = pd.DataFrame({
            "product_id": ["P1", "P2", "P3", "P4"],
            "annual_revenue": [100000.0, 50000.0, 15000.0, 5000.0]
        })
        res = ABCAnalyzer.classify_abc(df, value_col="annual_revenue")
        self.assertIn("abc_class", res.columns)
        # P1 is ~58.8% -> A
        self.assertEqual(res.loc[res["product_id"] == "P1", "abc_class"].values[0], "A")
        # P4 is bottom -> C
        self.assertEqual(res.loc[res["product_id"] == "P4", "abc_class"].values[0], "C")

    def test_xyz_classification(self):
        df = pd.DataFrame({
            "product_id": ["P1", "P2", "P3"],
            "daily_avg_demand": [10.0, 10.0, 10.0],
            "daily_demand_std": [2.0, 8.0, 15.0],  # CV: 0.2 (X), 0.8 (Y), 1.5 (Z)
            "abc_class": ["A", "B", "C"]
        })
        res = ABCAnalyzer.classify_xyz(df)
        self.assertEqual(res.loc[res["product_id"] == "P1", "xyz_class"].values[0], "X")
        self.assertEqual(res.loc[res["product_id"] == "P2", "xyz_class"].values[0], "Y")
        self.assertEqual(res.loc[res["product_id"] == "P3", "xyz_class"].values[0], "Z")
        self.assertEqual(res.loc[res["product_id"] == "P1", "abc_xyz_segment"].values[0], "AX")

    def test_stockout_risk_engine(self):
        df = pd.DataFrame({
            "product_id": ["P_Stockout", "P_BelowSS", "P_Healthy"],
            "current_stock": [0, 10, 100],
            "reserved_stock": [0, 0, 10],
            "daily_avg_demand": [5.0, 5.0, 5.0],
            "safety_stock": [20, 20, 20],
            "reorder_point": [50, 50, 50],
            "max_stock": [120, 120, 120],
            "unit_cost": [10.0, 10.0, 10.0],
            "annual_demand": [1825.0, 1825.0, 1825.0]
        })
        res = StockoutRiskEngine.calculate_metrics(df)
        
        # P_Stockout should have 100 risk score
        self.assertEqual(res.loc[res["product_id"] == "P_Stockout", "stockout_risk_score"].values[0], 100.0)
        self.assertEqual(res.loc[res["product_id"] == "P_Stockout", "stock_status"].values[0], "CRITICAL STOCKOUT")

        # P_BelowSS should be > 75
        self.assertGreater(res.loc[res["product_id"] == "P_BelowSS", "stockout_risk_score"].values[0], 75.0)

        # P_Healthy should be low risk
        self.assertLess(res.loc[res["product_id"] == "P_Healthy", "stockout_risk_score"].values[0], 40.0)

    def test_end_to_end_replenishment_pipeline(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            csv_file = Path(tmpdir) / "test_raw.csv"
            generate_raw_retail_csv(output_path=str(csv_file), num_records=200, seed=42)

            test_db_url = f"sqlite:///{Path(tmpdir) / 'test_rep.db'}"
            # Step 1: Ingestion
            ingestion = DataIngestionPipeline(raw_csv_path=str(csv_file), db_url=test_db_url)
            ingestion.run()

            # Step 2: Optimization
            optimizer = InventoryOptimizer(db_url=test_db_url, default_service_level=0.95)
            optimizer.optimize_all_products()

            # Step 3: Replenishment & ABC Risk
            planner = ReplenishmentPlanner(db_url=test_db_url)
            plan = planner.run_plan()

            self.assertIn("full_metrics", plan)
            self.assertIn("replenishment_orders", plan)
            metrics_df = plan["full_metrics"]
            self.assertIn("abc_class", metrics_df.columns)
            self.assertIn("stockout_risk_score", metrics_df.columns)


if __name__ == "__main__":
    unittest.main()
