import unittest
import numpy as np
import pandas as pd
import tempfile
from pathlib import Path

from forecasting.models import (
    SimpleMovingAverageForecaster,
    WeightedMovingAverageForecaster,
    SimpleExponentialSmoothingForecaster,
    HoltLinearTrendForecaster,
)
from forecasting.evaluator import ForecastEvaluator
from forecasting.engine import ForecastingEngine
from data_pipeline.ingest import DataIngestionPipeline
from sample_data.generate_raw_sample import generate_raw_retail_csv


class TestForecasting(unittest.TestCase):

    def setUp(self):
        # 60 days of synthetic demand with a subtle upward trend
        np.random.seed(42)
        dates = pd.date_range("2024-01-01", periods=60, freq="D")
        trend = np.linspace(10, 30, 60)
        noise = np.random.normal(0, 3, 60)
        demand = np.maximum(trend + noise, 0.0)
        self.series = pd.Series(demand, index=dates)

    def test_sma_forecaster(self):
        sma = SimpleMovingAverageForecaster(window=7)
        sma.fit(self.series.iloc[:-10])
        preds = sma.predict(steps=5)
        self.assertEqual(len(preds), 5)
        expected_mean = float(np.mean(self.series.iloc[-17:-10].values))
        self.assertAlmostEqual(preds[0], expected_mean, places=4)

    def test_wma_forecaster(self):
        wma = WeightedMovingAverageForecaster(window=5)
        wma.fit(self.series.iloc[:-10])
        preds = wma.predict(steps=5)
        self.assertEqual(len(preds), 5)
        self.assertGreater(preds[0], 0)

    def test_ses_forecaster(self):
        ses = SimpleExponentialSmoothingForecaster(alpha=None)
        ses.fit(self.series.iloc[:-10])
        self.assertTrue(ses.fitted)
        self.assertGreaterEqual(ses.alpha, 0.01)
        self.assertLessEqual(ses.alpha, 0.99)
        preds = ses.predict(steps=5)
        self.assertEqual(len(preds), 5)

    def test_holt_linear_forecaster(self):
        holt = HoltLinearTrendForecaster(alpha=None, beta=None)
        holt.fit(self.series.iloc[:-10])
        self.assertTrue(holt.fitted)
        preds = holt.predict(steps=5)
        self.assertEqual(len(preds), 5)
        # Verify non-negative demand
        self.assertTrue((preds >= 0).all())

    def test_evaluator_metrics(self):
        actual = np.array([10.0, 20.0, 30.0, 40.0])
        pred = np.array([12.0, 18.0, 33.0, 38.0])

        metrics = ForecastEvaluator.evaluate(actual, pred)
        self.assertIn("mae", metrics)
        self.assertIn("rmse", metrics)
        self.assertIn("mape", metrics)
        self.assertIn("smape", metrics)
        self.assertIn("tracking_signal", metrics)

        # MAE: mean(|2, -2, 3, -2|) = 9/4 = 2.25
        self.assertAlmostEqual(metrics["mae"], 2.25, places=2)

    def test_forecasting_engine_integration(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            csv_file = Path(tmpdir) / "test_raw.csv"
            generate_raw_retail_csv(output_path=str(csv_file), num_records=200, seed=42)

            test_db_url = f"sqlite:///{Path(tmpdir) / 'test_forecasting.db'}"
            # Ingest raw data first
            ingestion = DataIngestionPipeline(raw_csv_path=str(csv_file), db_url=test_db_url)
            ingestion.run()

            # Run forecasting engine
            engine = ForecastingEngine(db_url=test_db_url, test_days=14, forecast_horizon_days=14)
            summary_df = engine.execute_and_persist()

            self.assertFalse(summary_df.empty)
            self.assertIn("Champion Model", summary_df.columns)
            self.assertIn("RMSE", summary_df.columns)


if __name__ == "__main__":
    unittest.main()
