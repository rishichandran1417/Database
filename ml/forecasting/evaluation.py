"""
Evaluation metrics module for time-series forecasting.
Computes MAE, RMSE, and MAPE.
"""

from typing import Dict
import numpy as np


def mean_absolute_error(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    """Calculates Mean Absolute Error (MAE)."""
    y_true, y_pred = np.array(y_true), np.array(y_pred)
    return float(np.mean(np.abs(y_true - y_pred)))


def root_mean_squared_error(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    """Calculates Root Mean Squared Error (RMSE)."""
    y_true, y_pred = np.array(y_true), np.array(y_pred)
    return float(np.sqrt(np.mean((y_true - y_pred) ** 2)))


def mean_absolute_percentage_error(y_true: np.ndarray, y_pred: np.ndarray, eps: float = 1e-5) -> float:
    """
    Calculates Mean Absolute Percentage Error (MAPE).
    Handles zero values in y_true using epsilon smoothing to prevent division by zero.
    Returns value formatted as percentage (e.g. 12.5 for 12.5%).
    """
    y_true, y_pred = np.array(y_true, dtype=float), np.array(y_pred, dtype=float)
    denom = np.maximum(np.abs(y_true), eps)
    mape_val = np.mean(np.abs((y_true - y_pred) / denom)) * 100.0
    return float(round(mape_val, 2))


def evaluate_forecast(y_true: np.ndarray, y_pred: np.ndarray) -> Dict[str, float]:
    """Evaluates all metrics (MAE, RMSE, MAPE) and returns dictionary."""
    return {
        "mae": float(round(mean_absolute_error(y_true, y_pred), 2)),
        "rmse": float(round(root_mean_squared_error(y_true, y_pred), 2)),
        "mape": mean_absolute_percentage_error(y_true, y_pred),
    }
