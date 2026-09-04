import unittest
import math
import tempfile
from pathlib import Path
import pandas as pd
import numpy as np

from inventory_optimization.formulas import InventoryFormulas
from inventory_optimization.optimizer import InventoryOptimizer
from data_pipeline.ingest import DataIngestionPipeline
from sample_data.generate_raw_sample import generate_raw_retail_csv


class TestInventoryOptimization(unittest.TestCase):

    def test_z_score_lookup(self):
        z_95 = InventoryFormulas.get_z_score(0.95)
        self.assertAlmostEqual(z_95, 1.64485, places=4)

        z_99 = InventoryFormulas.get_z_score(0.99)
        self.assertAlmostEqual(z_99, 2.32635, places=4)

        with self.assertRaises(ValueError):
            InventoryFormulas.get_z_score(1.5)

    def test_safety_stock_constant_lead_time(self):
        # SS = Z * sigma_d * sqrt(L)
        # Z = 1.64485, sigma_d = 5, L = 9 -> SS = 1.64485 * 5 * 3 = 24.67
        ss = InventoryFormulas.calculate_safety_stock(
            daily_demand_std=5.0,
            lead_time_days=9.0,
            service_level=0.95
        )
        self.assertAlmostEqual(ss, 24.6728, places=2)

    def test_safety_stock_stochastic_lead_time(self):
        # Stochastic variance = L * sigma_d^2 + d_avg^2 * sigma_L^2
        ss_stochastic = InventoryFormulas.calculate_safety_stock(
            daily_demand_std=5.0,
            lead_time_days=9.0,
            service_level=0.95,
            lead_time_std=2.0,
            daily_demand_mean=10.0
        )
        self.assertGreater(ss_stochastic, 24.67)

    def test_reorder_point(self):
        # DDLT = 10 * 7 = 70. SS = 20. ROP = 90.
        rop = InventoryFormulas.calculate_reorder_point(
            daily_demand_mean=10.0,
            lead_time_days=7.0,
            safety_stock=20.0
        )
        self.assertEqual(rop, 90.0)

    def test_eoq_and_cost_minimization(self):
        # D = 10,000 units/year, S = $50/order, Unit Cost = $25, H = 20% -> Unit Holding Cost = $5/year
        # EOQ = sqrt((2 * 10,000 * 50) / 5) = sqrt(200,000) ≈ 447.21 units
        metrics = InventoryFormulas.calculate_eoq(
            annual_demand=10000.0,
            ordering_cost_s=50.0,
            unit_cost=25.0,
            holding_cost_rate_h=0.20
        )
        self.assertAlmostEqual(metrics["eoq"], 447.21, places=1)
        
        # At EOQ, Annual Ordering Cost ≈ Annual Holding Cost
        self.assertAlmostEqual(metrics["annual_ordering_cost"], metrics["annual_holding_cost"], delta=1.0)
        self.assertAlmostEqual(metrics["total_annual_inventory_cost"], 2236.07, delta=2.0)

    def test_inventory_optimizer_integration(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            csv_file = Path(tmpdir) / "test_raw.csv"
            generate_raw_retail_csv(output_path=str(csv_file), num_records=200, seed=42)

            test_db_url = f"sqlite:///{Path(tmpdir) / 'test_inv.db'}"
            # Ingest raw data first
            ingestion = DataIngestionPipeline(raw_csv_path=str(csv_file), db_url=test_db_url)
            ingestion.run()

            # Run inventory optimizer
            optimizer = InventoryOptimizer(db_url=test_db_url, default_service_level=0.95)
            results_df = optimizer.optimize_all_products()

            self.assertFalse(results_df.empty)
            self.assertIn("safety_stock", results_df.columns)
            self.assertIn("reorder_point", results_df.columns)
            self.assertIn("economic_order_qty", results_df.columns)
            self.assertTrue((results_df["safety_stock"] > 0).all())
            self.assertTrue((results_df["reorder_point"] >= results_df["safety_stock"]).all())


if __name__ == "__main__":
    unittest.main()
