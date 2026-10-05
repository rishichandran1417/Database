"""
Evaluation metrics module for time-series forecasting.
Computes MAE, RMSE, WAPE (Weighted Absolute Percentage Error), sMAPE (Symmetric MAPE), and Bias.
Robust against zero-demand observations in spare-parts inventory.
"""

from typing import Dict
import numpy as np


def mean_absolute_error(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    """Calculates Mean Absolute Error (MAE)."""
    y_true, y_pred = np.array(y_true, dtype=float), np.array(y_pred, dtype=float)
    return float(np.mean(np.abs(y_true - y_pred)))


def root_mean_squared_error(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    """Calculates Root Mean Squared Error (RMSE)."""
    y_true, y_pred = np.array(y_true, dtype=float), np.array(y_pred, dtype=float)
    return float(np.sqrt(np.mean((y_true - y_pred) ** 2)))


def weighted_absolute_percentage_error(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    """
    Calculates Weighted Absolute Percentage Error (WAPE / Volume-Weighted MAPE).
    Standard for zero-demand intermittent inventory because it divides total absolute error
    by total actual demand, avoiding division by zero for individual observations.
    """
    y_true, y_pred = np.array(y_true, dtype=float), np.array(y_pred, dtype=float)
    total_actual = np.sum(np.abs(y_true))
    if total_actual == 0:
        return 0.0
    wape_val = (np.sum(np.abs(y_true - y_pred)) / total_actual) * 100.0
    return float(round(wape_val, 2))


def symmetric_mean_absolute_percentage_error(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    """
    Calculates Symmetric Mean Absolute Percentage Error (sMAPE).
    Bounded between 0% and 200%. Handles zero values gracefully.
    """
    y_true, y_pred = np.array(y_true, dtype=float), np.array(y_pred, dtype=float)
    denom = (np.abs(y_true) + np.abs(y_pred)) / 2.0
    nonzero_mask = denom > 0
    if not np.any(nonzero_mask):
        return 0.0
    smape_val = np.mean(np.abs(y_true[nonzero_mask] - y_pred[nonzero_mask]) / denom[nonzero_mask]) * 100.0
    return float(round(smape_val, 2))


def mean_absolute_percentage_error(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    """
    Calculates Mean Absolute Percentage Error (MAPE) strictly on non-zero actual demand.
    Returns WAPE if all actual demand values are zero, preventing division-by-zero artifacts.
    """
    y_true, y_pred = np.array(y_true, dtype=float), np.array(y_pred, dtype=float)
    nonzero_mask = y_true > 0
    if not np.any(nonzero_mask):
        return weighted_absolute_percentage_error(y_true, y_pred)
    mape_val = np.mean(np.abs((y_true[nonzero_mask] - y_pred[nonzero_mask]) / y_true[nonzero_mask])) * 100.0
    return float(round(mape_val, 2))


def forecast_bias(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    """Calculates Mean Forecast Bias (Positive = over-forecasting, Negative = under-forecasting)."""
    y_true, y_pred = np.array(y_true, dtype=float), np.array(y_pred, dtype=float)
    return float(round(np.mean(y_pred - y_true), 2))


def evaluate_forecast(y_true: np.ndarray, y_pred: np.ndarray) -> Dict[str, float]:
    """Evaluates all statistically appropriate metrics and returns dictionary."""
    return {
        "mae": float(round(mean_absolute_error(y_true, y_pred), 2)),
        "rmse": float(round(root_mean_squared_error(y_true, y_pred), 2)),
        "wape": weighted_absolute_percentage_error(y_true, y_pred),
        "smape": symmetric_mean_absolute_percentage_error(y_true, y_pred),
        "mape": mean_absolute_percentage_error(y_true, y_pred),
        "bias": forecast_bias(y_true, y_pred),
    }

