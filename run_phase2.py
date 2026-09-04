"""
SupplyChainIQ - Phase 2 Runner Script: Demand Forecasting Engine
Executes time-series demand models (SMA, WMA, Single SES, Double Holt's Linear),
evaluates MAE/RMSE/MAPE on holdout test splits, selects champion models,
and loads 30-day forward predictions into PostgreSQL / SQLite database.
"""

import argparse
import sys
import pandas as pd
from sqlalchemy import text
from config import DATABASE_URL
from database.connection import get_engine
from forecasting.engine import ForecastingEngine


def display_forecast_samples(engine):
    print("\n" + "-" * 75)
    print("SAMPLE DATABASE FORECAST RECORDS (Actual vs Forecast on Test Period):")
    print("-" * 75)
    query_backtest = """
        SELECT product_id, DATE(forecast_date) as date, model_name,
               predicted_demand as predicted, actual_demand as actual, mae, rmse, mape
        FROM forecasts
        WHERE actual_demand IS NOT NULL
        LIMIT 6;
    """
    with engine.connect() as conn:
        df_backtest = pd.read_sql(query_backtest, conn)
        print(df_backtest.to_string(index=False))

    print("\n" + "-" * 75)
    print("SAMPLE FORWARD FORECAST RECORDS (Next 30 Days Out-of-Sample Horizon):")
    print("-" * 75)
    query_forward = """
        SELECT product_id, DATE(forecast_date) as forecast_date, model_name,
               predicted_demand as forward_forecast
        FROM forecasts
        WHERE actual_demand IS NULL
        LIMIT 6;
    """
    with engine.connect() as conn:
        df_forward = pd.read_sql(query_forward, conn)
        print(df_forward.to_string(index=False))
    print("=" * 75 + "\n")


def main():
    parser = argparse.ArgumentParser(description="SupplyChainIQ Phase 2: Demand Forecasting Engine")
    parser.add_argument("--db-url", type=str, default=DATABASE_URL, help="Database connection URL")
    parser.add_argument("--test-days", type=int, default=30, help="Number of holdout days for test evaluation")
    parser.add_argument("--horizon", type=int, default=30, help="Number of future days to forecast")
    args = parser.parse_args()

    print("\n" + "=" * 75)
    print("       SUPPLYCHAINIQ - PHASE 2: DEMAND FORECASTING ENGINE      ")
    print("=" * 75)

    engine_runner = ForecastingEngine(
        db_url=args.db_url,
        test_days=args.test_days,
        forecast_horizon_days=args.horizon
    )

    summary_df = engine_runner.execute_and_persist()

    print("\n" + "=" * 75)
    print("         PRODUCT-LEVEL FORECAST MODEL PERFORMANCE BENCHMARK     ")
    print("=" * 75)
    print(summary_df.to_string(index=False))

    db_engine = get_engine(args.db_url)
    display_forecast_samples(db_engine)
    db_engine.dispose()


if __name__ == "__main__":
    main()
