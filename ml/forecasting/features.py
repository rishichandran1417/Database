"""
Feature engineering module for time-series ML demand forecasting.
Constructs lag features, rolling window metrics, and calendar features from historical demand consumption.
"""

from typing import List
import pandas as pd
import numpy as np


FEATURE_COLUMNS = [
    "lag_1",
    "lag_7",
    "lag_14",
    "lag_28",
    "rolling_mean_7",
    "rolling_mean_14",
    "rolling_mean_28",
    "rolling_std_28",
    "day_of_week",
    "day_of_month",
    "month",
    "quarter",
    "year",
]


def build_time_series_features(df: pd.DataFrame, target_col: str = "quantity_consumed") -> pd.DataFrame:
    """
    Given a DataFrame containing historical consumption data with columns ['part_id', 'date', 'quantity_consumed'],
    computes time-series lag, rolling window, and calendar features per part_id.
    """
    if df.empty:
        return df

    df = df.copy()
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values(by=["part_id", "date"]).reset_index(drop=True)

    # Group by part_id for lag and rolling calculations
    grouped = df.groupby("part_id")[target_col]

    # Lags
    df["lag_1"] = grouped.shift(1)
    df["lag_7"] = grouped.shift(7)
    df["lag_14"] = grouped.shift(14)
    df["lag_28"] = grouped.shift(28)

    # Rolling statistics (using closed='left' or shift(1) to avoid data leakage)
    df["rolling_mean_7"] = df.groupby("part_id")[target_col].transform(
        lambda x: x.shift(1).rolling(window=7, min_periods=1).mean()
    )
    df["rolling_mean_14"] = df.groupby("part_id")[target_col].transform(
        lambda x: x.shift(1).rolling(window=14, min_periods=1).mean()
    )
    df["rolling_mean_28"] = df.groupby("part_id")[target_col].transform(
        lambda x: x.shift(1).rolling(window=28, min_periods=1).mean()
    )
    df["rolling_std_28"] = df.groupby("part_id")[target_col].transform(
        lambda x: x.shift(1).rolling(window=28, min_periods=1).std()
    ).fillna(0.0)

    # Calendar features
    df["day_of_week"] = df["date"].dt.dayofweek
    df["day_of_month"] = df["date"].dt.day
    df["month"] = df["date"].dt.month
    df["quarter"] = df["date"].dt.quarter
    df["year"] = df["date"].dt.year

    # Fill NaNs in lag features gracefully with rolling mean or 0
    for lag in ["lag_1", "lag_7", "lag_14", "lag_28"]:
        df[lag] = df[lag].fillna(df["rolling_mean_7"]).fillna(0.0)

    return df
