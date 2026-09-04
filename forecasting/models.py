import numpy as np
import pandas as pd
from typing import Dict, Tuple, Optional
from scipy.optimize import minimize


class BaseForecaster:
    """Base class for time-series demand forecasters."""

    def __init__(self, name: str):
        self.name = name
        self.fitted = False

    def fit(self, train_series: pd.Series):
        raise NotImplementedError

    def predict(self, steps: int) -> np.ndarray:
        raise NotImplementedError


class SimpleMovingAverageForecaster(BaseForecaster):
    """
    Simple Moving Average (SMA) Forecaster.
    Forecasts future demand as the unweighted mean of the last `window` periods.
    """

    def __init__(self, window: int = 7):
        super().__init__(name=f"SMA_{window}")
        self.window = window
        self.last_values = None

    def fit(self, train_series: pd.Series):
        values = train_series.values
        if len(values) < self.window:
            self.last_values = values
        else:
            self.last_values = values[-self.window:]
        self.fitted = True
        return self

    def predict(self, steps: int) -> np.ndarray:
        if not self.fitted:
            raise ValueError("Model is not fitted yet.")
        mean_val = float(np.mean(self.last_values)) if len(self.last_values) > 0 else 0.0
        return np.full(steps, max(mean_val, 0.0))


class WeightedMovingAverageForecaster(BaseForecaster):
    """
    Weighted Moving Average (WMA) Forecaster.
    Assigns linearly increasing weights to recent observations.
    """

    def __init__(self, window: int = 7):
        super().__init__(name=f"WMA_{window}")
        self.window = window
        self.last_values = None
        self.weights = np.arange(1, window + 1)
        self.weights = self.weights / self.weights.sum()

    def fit(self, train_series: pd.Series):
        values = train_series.values
        if len(values) < self.window:
            w = np.arange(1, len(values) + 1)
            w = w / w.sum()
            self.weights = w
            self.last_values = values
        else:
            self.last_values = values[-self.window:]
        self.fitted = True
        return self

    def predict(self, steps: int) -> np.ndarray:
        if not self.fitted:
            raise ValueError("Model is not fitted yet.")
        weighted_val = float(np.dot(self.last_values, self.weights))
        return np.full(steps, max(weighted_val, 0.0))


class SimpleExponentialSmoothingForecaster(BaseForecaster):
    """
    Simple Exponential Smoothing (SES / Single Exp Smoothing).
    Formula: F_{t+1} = α * Y_t + (1 - α) * F_t
    Optimizes smoothing parameter α ∈ (0, 1) via MSE minimization if alpha is None.
    """

    def __init__(self, alpha: Optional[float] = None):
        super().__init__(name=f"SES_{alpha if alpha else 'auto'}")
        self.alpha = alpha
        self.last_level = None

    def _fit_ses(self, series: np.ndarray, alpha: float) -> Tuple[np.ndarray, float]:
        n = len(series)
        smoothed = np.zeros(n)
        smoothed[0] = series[0]
        for t in range(1, n):
            smoothed[t] = alpha * series[t - 1] + (1 - alpha) * smoothed[t - 1]
        return smoothed, smoothed[-1]

    def fit(self, train_series: pd.Series):
        values = train_series.values.astype(float)
        if len(values) == 0:
            self.last_level = 0.0
            self.fitted = True
            return self

        if self.alpha is None:
            # Optimize alpha to minimize one-step-ahead sum of squared errors
            def loss(a):
                if a[0] <= 0 or a[0] >= 1:
                    return 1e9
                smoothed, _ = self._fit_ses(values, a[0])
                return np.mean((values[1:] - smoothed[1:]) ** 2)

            res = minimize(loss, x0=[0.3], bounds=[(0.01, 0.99)], method="L-BFGS-B")
            best_alpha = float(res.x[0]) if res.success else 0.3
            self.alpha = round(best_alpha, 3)
            self.name = f"SES_alpha={self.alpha}"

        _, self.last_level = self._fit_ses(values, self.alpha)
        self.fitted = True
        return self

    def predict(self, steps: int) -> np.ndarray:
        if not self.fitted:
            raise ValueError("Model is not fitted yet.")
        return np.full(steps, max(float(self.last_level), 0.0))


class HoltLinearTrendForecaster(BaseForecaster):
    """
    Double Exponential Smoothing (Holt's Linear Trend Model).
    Level:  L_t = alpha * Y_t + (1 - alpha) * (L_{t-1} + T_{t-1})
    Trend:  T_t = beta * (L_t - L_{t-1}) + (1 - beta) * T_{t-1}
    Forecast: F_{t+h} = L_t + h * T_t
    """

    def __init__(self, alpha: Optional[float] = None, beta: Optional[float] = None):
        super().__init__(name=f"HoltLinear_{alpha if alpha else 'auto'}")
        self.alpha = alpha
        self.beta = beta
        self.last_level = 0.0
        self.last_trend = 0.0

    def fit(self, train_series: pd.Series):
        values = train_series.values.astype(float)
        n = len(values)
        if n < 2:
            self.last_level = float(values[0]) if n == 1 else 0.0
            self.last_trend = 0.0
            self.fitted = True
            return self

        def run_holt(a, b):
            levels = np.zeros(n)
            trends = np.zeros(n)
            levels[0] = values[0]
            trends[0] = values[1] - values[0]
            for t in range(1, n):
                levels[t] = a * values[t] + (1 - a) * (levels[t - 1] + trends[t - 1])
                trends[t] = b * (levels[t] - levels[t - 1]) + (1 - b) * trends[t - 1]
            return levels, trends

        if self.alpha is None or self.beta is None:
            def loss(params):
                a, b = params
                levels, trends = run_holt(a, b)
                one_step_preds = levels[:-1] + trends[:-1]
                return np.mean((values[1:] - one_step_preds) ** 2)

            res = minimize(loss, x0=[0.3, 0.1], bounds=[(0.01, 0.99), (0.01, 0.99)], method="L-BFGS-B")
            if res.success:
                self.alpha, self.beta = round(float(res.x[0]), 3), round(float(res.x[1]), 3)
            else:
                self.alpha, self.beta = 0.3, 0.1
            self.name = f"HoltLinear_alpha={self.alpha}_beta={self.beta}"

        levels, trends = run_holt(self.alpha, self.beta)
        self.last_level = levels[-1]
        self.last_trend = trends[-1]
        self.fitted = True
        return self

    def predict(self, steps: int) -> np.ndarray:
        if not self.fitted:
            raise ValueError("Model is not fitted yet.")
        h = np.arange(1, steps + 1)
        preds = self.last_level + h * self.last_trend
        return np.maximum(preds, 0.0)  # Demand cannot be negative
