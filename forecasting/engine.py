import logging
import datetime
from typing import Dict, List, Tuple, Optional
import pandas as pd
import numpy as np
from sqlalchemy import text
from sqlalchemy.orm import Session

from config import DATABASE_URL
from database.connection import get_engine, get_session
from database.models import Product, Sale, Forecast
from forecasting.models import (
    SimpleMovingAverageForecaster,
    WeightedMovingAverageForecaster,
    SimpleExponentialSmoothingForecaster,
    HoltLinearTrendForecaster,
)
from forecasting.evaluator import ForecastEvaluator

logger = logging.getLogger("SupplyChainIQ.Forecasting")


class ForecastingEngine:
    """
    End-to-End Demand Forecasting Engine:
    1. Extracts sales history from database
    2. Aggregates into continuous daily time-series with zero-fill for non-sales days
    3. Executes strictly time-based train/test splits
    4. Evaluates multiple candidate algorithms per product (SMA, WMA, SES, Holt's Linear)
    5. Benchmarks error metrics (MAE, RMSE, MAPE, SMAPE, Tracking Signal)
    6. Identifies the champion model per product and persists forecast results to the database
    """

    def __init__(self, db_url: Optional[str] = None, test_days: int = 30, forecast_horizon_days: int = 30):
        self.db_url = db_url or DATABASE_URL
        self.test_days = test_days
        self.forecast_horizon_days = forecast_horizon_days
        self.engine = get_engine(self.db_url)

    def extract_product_time_series(self) -> Dict[str, pd.Series]:
        """
        Extracts sales data grouped by product_id and resampled to a continuous daily frequency.
        """
        query = """
            SELECT s.product_id, DATE(s.sale_date) as sale_date, SUM(s.quantity) as total_qty
            FROM sales s
            GROUP BY s.product_id, DATE(s.sale_date)
            ORDER BY s.product_id, sale_date ASC;
        """
        with self.engine.connect() as conn:
            df = pd.read_sql(query, conn)

        if df.empty:
            raise ValueError("No sales data found in the database. Run Phase 1 ingestion first.")

        df["sale_date"] = pd.to_datetime(df["sale_date"])
        min_date = df["sale_date"].min()
        max_date = df["sale_date"].max()
        full_date_idx = pd.date_range(start=min_date, end=max_date, freq="D")

        product_series = {}
        for prod_id, group in df.groupby("product_id"):
            s = group.set_index("sale_date")["total_qty"].reindex(full_date_idx, fill_value=0)
            product_series[prod_id] = s

        logger.info(f"Loaded continuous time-series for {len(product_series)} products (Span: {min_date.date()} to {max_date.date()}, {len(full_date_idx)} days).")
        return product_series

    def run_product_forecast(self, prod_id: str, series: pd.Series) -> Dict:
        """
        Splits series into train/test, evaluates all candidate models, and forecasts forward.
        """
        n_points = len(series)
        test_size = min(self.test_days, max(int(n_points * 0.2), 7))
        train_series = series.iloc[:-test_size]
        test_series = series.iloc[-test_size:]

        candidate_models = [
            SimpleMovingAverageForecaster(window=7),
            SimpleMovingAverageForecaster(window=14),
            WeightedMovingAverageForecaster(window=7),
            SimpleExponentialSmoothingForecaster(alpha=None),  # Auto-optimized
            HoltLinearTrendForecaster(alpha=None, beta=None),  # Auto-optimized
        ]

        model_results = []
        for model in candidate_models:
            # Fit on training period
            model.fit(train_series)
            test_preds = model.predict(steps=len(test_series))
            eval_metrics = ForecastEvaluator.evaluate(test_series.values, test_preds)

            # Refit on all historical data for forward-looking forecast
            model.fit(series)
            future_preds = model.predict(steps=self.forecast_horizon_days)

            model_results.append({
                "model_name": model.name,
                "metrics": eval_metrics,
                "test_preds": test_preds,
                "future_preds": future_preds,
                "model_obj": model
            })

        # Select champion model based on lowest RMSE on test set
        champion = min(model_results, key=lambda x: x["metrics"]["rmse"])

        return {
            "product_id": prod_id,
            "train_series": train_series,
            "test_series": test_series,
            "candidate_results": model_results,
            "champion_model": champion["model_name"],
            "champion_metrics": champion["metrics"],
            "future_forecast": champion["future_preds"]
        }

    def execute_and_persist(self) -> pd.DataFrame:
        """
        Runs forecasting for all products, saves records to 'forecasts' table, and returns a summary DataFrame.
        """
        product_series = self.extract_product_time_series()
        all_forecast_records = []
        summary_rows = []

        now_utc = datetime.datetime.now(datetime.timezone.utc)

        for prod_id, series in product_series.items():
            res = self.run_product_forecast(prod_id, series)
            test_series = res["test_series"]
            champ_name = res["champion_model"]
            metrics = res["champion_metrics"]

            summary_rows.append({
                "Product ID": prod_id,
                "Champion Model": champ_name,
                "MAE": metrics["mae"],
                "RMSE": metrics["rmse"],
                "WMAPE (%)": f"{metrics['mape']}%",
                "SMAPE (%)": f"{metrics['smape']}%",
                "Tracking Signal": metrics["tracking_signal"],
                "Avg Daily Demand": round(float(series.mean()), 2),
                "Next 30D Forecast": int(np.sum(res["future_forecast"])),
            })

            # Record 1: Historical validation backtest records for champion model
            champ_res = next(m for m in res["candidate_results"] if m["model_name"] == champ_name)
            for dt, act_val, pred_val in zip(test_series.index, test_series.values, champ_res["test_preds"]):
                all_forecast_records.append({
                    "product_id": prod_id,
                    "forecast_date": dt,
                    "model_name": champ_name,
                    "predicted_demand": round(float(pred_val), 2),
                    "actual_demand": round(float(act_val), 2),
                    "mae": metrics["mae"],
                    "rmse": metrics["rmse"],
                    "mape": metrics["mape"],
                    "created_at": now_utc
                })

            # Record 2: Forward 30-day daily forecasts
            last_date = series.index[-1]
            future_dates = pd.date_range(start=last_date + datetime.timedelta(days=1), periods=self.forecast_horizon_days, freq="D")
            for f_date, pred_val in zip(future_dates, res["future_forecast"]):
                all_forecast_records.append({
                    "product_id": prod_id,
                    "forecast_date": f_date,
                    "model_name": champ_name,
                    "predicted_demand": round(float(pred_val), 2),
                    "actual_demand": None,
                    "mae": metrics["mae"],
                    "rmse": metrics["rmse"],
                    "mape": metrics["mape"],
                    "created_at": now_utc
                })

        forecasts_df = pd.DataFrame(all_forecast_records)

        # Clear existing forecast table and persist
        with self.engine.begin() as conn:
            conn.execute(text("DELETE FROM forecasts;"))
            forecasts_df.to_sql("forecasts", con=conn, if_exists="append", index=False, chunksize=1000)

        logger.info(f"Persisted {len(forecasts_df)} forecast entries into database.")
        
        self.engine.dispose()
        return pd.DataFrame(summary_rows)
