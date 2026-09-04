import numpy as np
from typing import Dict


class ForecastEvaluator:
    """
    Evaluates forecasting accuracy using standard supply chain error metrics:
    - MAE: Mean Absolute Error
    - RMSE: Root Mean Squared Error
    - WMAPE: Weighted Mean Absolute Percentage Error (sum(|A - F|) / sum(A) * 100) -> Industry Standard for intermittent demand
    - SMAPE: Symmetric Mean Absolute Percentage Error (2 * |F - A| / (|A| + |F|) * 100)
    - Tracking Signal: Cumulative Forecast Error / MAD (detects systematic over/under forecasting)
    """

    @staticmethod
    def calculate_mae(actual: np.ndarray, predicted: np.ndarray) -> float:
        return float(np.mean(np.abs(actual - predicted)))

    @staticmethod
    def calculate_rmse(actual: np.ndarray, predicted: np.ndarray) -> float:
        return float(np.sqrt(np.mean((actual - predicted) ** 2)))

    @staticmethod
    def calculate_wmape(actual: np.ndarray, predicted: np.ndarray) -> float:
        total_actual = float(np.sum(actual))
        if total_actual == 0:
            return 0.0 if np.sum(predicted) == 0 else 100.0
        return float(np.sum(np.abs(actual - predicted)) / total_actual * 100.0)

    @staticmethod
    def calculate_smape(actual: np.ndarray, predicted: np.ndarray) -> float:
        denom = (np.abs(actual) + np.abs(predicted)) / 2.0
        # If both actual and predicted are 0, error is 0
        zero_mask = (actual == 0) & (predicted == 0)
        denom = np.where(denom == 0, 1.0, denom)
        smape_elements = np.where(zero_mask, 0.0, np.abs(predicted - actual) / denom)
        return float(np.mean(smape_elements) * 100.0)

    @staticmethod
    def calculate_tracking_signal(actual: np.ndarray, predicted: np.ndarray) -> float:
        errors = actual - predicted
        mad = np.mean(np.abs(errors))
        if mad == 0:
            return 0.0
        return float(np.sum(errors) / mad)

    @classmethod
    def evaluate(cls, actual: np.ndarray, predicted: np.ndarray) -> Dict[str, float]:
        actual = np.asarray(actual, dtype=float)
        predicted = np.asarray(predicted, dtype=float)

        mae = cls.calculate_mae(actual, predicted)
        rmse = cls.calculate_rmse(actual, predicted)
        wmape = cls.calculate_wmape(actual, predicted)
        smape = cls.calculate_smape(actual, predicted)
        tracking_signal = cls.calculate_tracking_signal(actual, predicted)

        return {
            "mae": round(mae, 3),
            "rmse": round(rmse, 3),
            "mape": round(wmape, 2),   # WMAPE as the practical supply chain MAPE
            "smape": round(smape, 2),
            "tracking_signal": round(tracking_signal, 2),
        }
