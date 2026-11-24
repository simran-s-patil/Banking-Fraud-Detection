"""Unit and integration tests for the prediction interface (ml/predict.py)."""
from pathlib import Path
import tempfile
import pandas as pd
import pytest

from ml.config import (
    DEFAULT_ENCODER_PATH,
    DEFAULT_MODEL_PATH,
    MODEL_VERSION,
    PRED_FRAUDULENT,
    PRED_LEGITIMATE,
    RISK_HIGH,
    RISK_LOW,
    RISK_MEDIUM,
)
from ml.predict import FraudPredictor, predict_batch, predict_transaction


@pytest.fixture
def valid_engineered_record() -> dict:
    """Creates a complete engineered feature record."""
    return {
        "TransactionID": 7001,
        "amount": 2500.0,
        "amount_log": 7.8244,
        "amount_zscore_sender": 0.1,
        "hour_of_day": 12,
        "day_of_week": 1,
        "is_night": 0,
        "is_festival_day": 0,
        "sender_account_age_days": 200,
        "has_sender_history": 1,
        "sender_txn_count_10m": 0,
        "sender_txn_count_60m": 1,
        "sender_txn_count_1440m": 2,
        "sender_amount_sum_60m": 2500.0,
        "is_new_receiver": 0,
        "sender_fanout_60m": 1.0,
        "sender_fanout_1440m": 2.0,
        "is_high_risk_category": 0,
        "is_new_merchant_for_customer": 0,
        "has_device_id": 1,
        "has_ip_address": 1,
        "has_location": 1,
        "has_card_token": 0,
        "is_merchant_missing": 1,
        "device_changed_for_account": 0,
        "location_changed_for_account": 0,
        "has_device_history": 1,
        "merchant_risk_rate": 0.0306,
        "sender_account_type": "Savings",
        "receiver_shape": "account_only",
        "merchant_category": "NOT_APPLICABLE",
    }


def test_predict_transaction_contract_fields(valid_engineered_record):
    """Verify all 6 required Person 1 contract fields are present and valid."""
    result = predict_transaction(valid_engineered_record, explain=False)

    assert result["transaction_id"] == 7001
    assert isinstance(result["fraud_probability"], float)
    assert 0.0 <= result["fraud_probability"] <= 1.0
    assert result["prediction"] in (PRED_LEGITIMATE, PRED_FRAUDULENT)
    assert result["model_version"] == MODEL_VERSION
    assert result["risk_status"] in (RISK_LOW, RISK_MEDIUM, RISK_HIGH)
    assert isinstance(result["merchant_risk_rate"], float)
    assert "explanation" not in result


def test_predict_transaction_series_and_df(valid_engineered_record):
    """Verify input flexibility: accepts Series or DataFrame."""
    s = pd.Series(valid_engineered_record)
    res_s = predict_transaction(s)
    assert res_s["transaction_id"] == 7001

    df = pd.DataFrame([valid_engineered_record])
    res_df = predict_transaction(df)
    assert res_df["transaction_id"] == 7001


def test_predict_transaction_with_explanation(valid_engineered_record):
    """Verify on-demand SHAP explanation is attached when explain=True."""
    result = predict_transaction(valid_engineered_record, explain=True)
    assert "explanation" in result
    assert "top_reasons" in result["explanation"]
    assert len(result["explanation"]["top_reasons"]) > 0


def test_predict_transaction_invalid_inputs():
    """Verify type checking and empty input rejection."""
    with pytest.raises(TypeError):
        predict_transaction(12345)

    with pytest.raises(ValueError):
        predict_transaction(pd.DataFrame())

    with pytest.raises(ValueError, match=r"(Missing required|missing required)"):
        predict_transaction({"TransactionID": 101, "amount": 50.0})


def test_predict_batch_multi_rows(valid_engineered_record):
    """Verify batch inference preserves ordering and scores multiple items."""
    rec1 = valid_engineered_record.copy()
    rec1["TransactionID"] = 8001
    rec2 = valid_engineered_record.copy()
    rec2["TransactionID"] = 8002
    rec3 = valid_engineered_record.copy()
    rec3["TransactionID"] = 8003

    batch = [rec1, rec2, rec3]
    results = predict_batch(batch, explain=False)

    assert len(results) == 3
    assert [r["transaction_id"] for r in results] == [8001, 8002, 8003]
    for r in results:
        assert 0.0 <= r["fraud_probability"] <= 1.0
        assert r["model_version"] == MODEL_VERSION


def test_predict_batch_empty():
    """Verify empty batch returns empty list."""
    assert predict_batch([]) == []
    assert predict_batch(pd.DataFrame()) == []


def test_predict_batch_error_handling(valid_engineered_record):
    """Verify error modes: raise vs coerce."""
    invalid_rec = {"TransactionID": 999, "invalid": True}
    batch = [valid_engineered_record, invalid_rec]

    # Mode 1: raise
    with pytest.raises(ValueError):
        predict_batch(batch, errors="raise")

    # Mode 2: coerce
    coerced = predict_batch(batch, errors="coerce")
    assert len(coerced) == 2
    assert coerced[0]["transaction_id"] == valid_engineered_record["TransactionID"]
    assert coerced[1]["transaction_id"] == 999
    assert coerced[1]["status"] == "FAILED"
    assert "error" in coerced[1]


def test_artifact_integrity_missing_files():
    """Verify clean errors when model or encoder files are missing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        fake_model = Path(tmpdir) / "non_existent_model.joblib"
        with pytest.raises(FileNotFoundError, match="Model artifact not found"):
            FraudPredictor(model_path=fake_model)

        fake_encoder = Path(tmpdir) / "non_existent_encoder.json"
        with pytest.raises(FileNotFoundError, match="Merchant encoder artifact not found"):
            FraudPredictor(encoder_path=fake_encoder)


def test_real_dataset_integration():
    """Integration test: runs actual saved model and encoder on a real cached row."""
    raw_path = Path(__file__).resolve().parents[1] / "ml" / "data" / "raw_features.csv"
    if not raw_path.exists():
        pytest.skip("ml/data/raw_features.csv not present for integration test")

    df = pd.read_csv(raw_path, nrows=5, parse_dates=["TransactionTimestamp", "SenderAccountCreatedAt"])
    results = predict_batch(df, explain=False)

    assert len(results) == 5
    for r in results:
        assert isinstance(r["transaction_id"], int)
        assert 0.0 <= r["fraud_probability"] <= 1.0
        assert r["prediction"] in (PRED_LEGITIMATE, PRED_FRAUDULENT)
        assert r["risk_status"] in (RISK_LOW, RISK_MEDIUM, RISK_HIGH)
