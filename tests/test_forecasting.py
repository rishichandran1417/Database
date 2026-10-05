"""
Unit tests for ML Demand Forecasting features, evaluation metrics, and API endpoints.
"""

from datetime import date, timedelta
import pandas as pd
import numpy as np
from fastapi.testclient import TestClient

from main import app
from ml.forecasting.features import build_time_series_features, FEATURE_COLUMNS
from ml.forecasting.evaluation import evaluate_forecast, mean_absolute_percentage_error
from ml.forecasting.predict import predict_demand_for_part

client = TestClient(app)


def test_feature_engineering():
    start = date(2026, 1, 1)
    dates = [start + timedelta(days=i) for i in range(40)]
    df_raw = pd.DataFrame({
        "part_id": [1] * 40,
        "date": dates,
        "quantity_consumed": np.random.randint(1, 10, size=40),
        "depot": ["KSRTC Central Stores"] * 40,
    })

    df_feat = build_time_series_features(df_raw)
    for col in FEATURE_COLUMNS:
        assert col in df_feat.columns, f"Missing feature column {col}"
    assert len(df_feat) == 40
    assert df_feat["month"].iloc[0] == 1


def test_evaluation_metrics():
    y_true = np.array([10, 20, 30, 40, 50])
    y_pred = np.array([12, 18, 33, 38, 52])
    metrics = evaluate_forecast(y_true, y_pred)
    assert "mae" in metrics
    assert "rmse" in metrics
    assert "mape" in metrics
    assert metrics["mae"] > 0
    assert metrics["rmse"] > 0
    assert metrics["mape"] >= 0


def test_forecast_prediction_struct():
    res = predict_demand_for_part(part_id=1, forecast_horizon=30)
    assert res["part_id"] == "1"
    assert "model" in res
    assert res["forecast_horizon"] == 30
    assert len(res["forecast"]) == 30
    assert "total_forecast" in res
    assert "mape" in res


def test_forecast_api_endpoint():
    response = client.get("/api/v1/db/forecast/1")
    assert response.status_code == 200
    data = response.json()
    assert data["part_id"] == "1"
    assert data["forecast_horizon"] == 30
    assert isinstance(data["forecast"], list)
    assert "total_forecast" in data
    assert "mape" in data


def test_forecast_probe_endpoint():
    res_probe = client.get("/forecast")
    assert res_probe.status_code == 200
    data_probe = res_probe.json()
    assert data_probe["status"] == "ok"
    assert data_probe["service"] == "ML Forecasting Service"
    assert data_probe["model"] == "XGBoost"

    res_api_probe = client.get("/api/v1/db/forecast")
    assert res_api_probe.status_code == 200
    assert res_api_probe.json()["status"] == "ok"


