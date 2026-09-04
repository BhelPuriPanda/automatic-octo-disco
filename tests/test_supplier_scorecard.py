import unittest
import tempfile
from pathlib import Path
import pandas as pd
import numpy as np

from supplier_scorecard.scorer import SupplierScorer
from supplier_scorecard.engine import SupplierScorecardEngine
from data_pipeline.ingest import DataIngestionPipeline
from sample_data.generate_raw_sample import generate_raw_retail_csv


class TestSupplierScorecard(unittest.TestCase):

    def test_perfect_supplier_scoring(self):
        # 100% OTIF, 0 delay, 0 defects, 1.0 cost ratio
        score = SupplierScorer.calculate_score(
            total_orders=50,
            on_time_in_full_orders=50,
            on_time_orders=50,
            avg_delay_days=0.0,
            lead_time_std=0.0,
            total_received_qty=5000,
            total_defect_qty=0,
            cost_ratio=1.0
        )
        self.assertEqual(score["composite_score"], 100.0)
        self.assertEqual(score["tier"], "Tier 1 (Platinum)")
        self.assertEqual(score["risk_level"], "Low Risk / Preferred")

    def test_poor_supplier_scoring(self):
        # 50% OTIF, 5 days avg delay, 4% defects
        score = SupplierScorer.calculate_score(
            total_orders=50,
            on_time_in_full_orders=25,
            on_time_orders=25,
            avg_delay_days=5.0,
            lead_time_std=3.0,
            total_received_qty=5000,
            total_defect_qty=200,
            cost_ratio=1.2
        )
        self.assertLess(score["composite_score"], 65.0)
        self.assertEqual(score["tier"], "Tier 4 (At Risk)")

    def test_supplier_scorecard_engine_integration(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            csv_file = Path(tmpdir) / "test_raw.csv"
            generate_raw_retail_csv(output_path=str(csv_file), num_records=200, seed=42)

            test_db_url = f"sqlite:///{Path(tmpdir) / 'test_sup.db'}"
            # Ingestion generates suppliers and POs
            ingestion = DataIngestionPipeline(raw_csv_path=str(csv_file), db_url=test_db_url)
            ingestion.run()

            engine = SupplierScorecardEngine(db_url=test_db_url)
            scorecard_df = engine.generate_scorecard()

            self.assertFalse(scorecard_df.empty)
            self.assertIn("composite_score", scorecard_df.columns)
            self.assertIn("otif_score (40%)", scorecard_df.columns)
            self.assertIn("tier", scorecard_df.columns)


if __name__ == "__main__":
    unittest.main()
