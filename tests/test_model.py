"""Unit tests for trained model artifacts and inference pipeline."""
from pathlib import Path
import joblib
import json
import numpy as np
import pandas as pd
import pytest

from ml.features import ALL_NUMERIC_FEATURES, CATEGORICAL_FEATURES, MerchantRiskEncoder

ROOT = Path(__file__).resolve().parents[1]
RF_MODEL_PATH = ROOT / "ml" / "models" / "random_forest_full_disposable_33070.joblib"
RF_SIDECAR_PATH = ROOT / "ml" / "models" / "random_forest_full_disposable_33070.json"
MERCHANT_ENCODER_PATH = ROOT / "ml" / "models" / "merchant_risk_encoder_disposable_33070.json"


@pytest.fixture
def loaded_rf_pipeline():
    assert RF_MODEL_PATH.exists(), f"Model file not found at {RF_MODEL_PATH}"
    return joblib.load(RF_MODEL_PATH)


@pytest.fixture
def model_sidecar():
    assert RF_SIDECAR_PATH.exists(), f"Sidecar JSON not found at {RF_SIDECAR_PATH}"
    with open(RF_SIDECAR_PATH) as f:
        return json.load(f)


@pytest.fixture
def dummy_inference_batch(model_sidecar):
    """Creates a 5-row synthetic DataFrame with all expected features in the correct order."""
    feature_cols = model_sidecar["feature_columns"]
    data = {}
    for col in ALL_NUMERIC_FEATURES:
        data[col] = [100.0, 5000.0, 25.0, 75000.0, 10.0]
    data["sender_account_type"] = ["Savings", "Savings", "Current", "Current", "Savings"]
    data["receiver_shape"] = ["account_only", "external_upi_only", "NOT_APPLICABLE", "NOT_APPLICABLE", "account_and_upi"]
    data["merchant_category"] = ["NOT_APPLICABLE", "NOT_APPLICABLE", "Electronics", "Gaming", "Jewellery"]
    data["merchant_risk_rate"] = [0.03, 0.03, 0.18, 0.14, 0.03]

    df = pd.DataFrame(data)
    return df[feature_cols]


def test_model_loading_and_type(loaded_rf_pipeline):
    from sklearn.pipeline import Pipeline
    assert isinstance(loaded_rf_pipeline, Pipeline)
    assert "preprocess" in loaded_rf_pipeline.named_steps
    assert "model" in loaded_rf_pipeline.named_steps


def test_sidecar_consistency(model_sidecar):
    assert model_sidecar["model_name"] == "random_forest"
    assert model_sidecar["threshold"] == 0.21
    assert model_sidecar["random_seed"] == 42
    assert len(model_sidecar["feature_columns"]) == 30

    expected_cols = ALL_NUMERIC_FEATURES + CATEGORICAL_FEATURES
    assert model_sidecar["feature_columns"] == expected_cols


def test_model_predict_proba_range_and_shape(loaded_rf_pipeline, dummy_inference_batch):
    probs = loaded_rf_pipeline.predict_proba(dummy_inference_batch)

    # Probabilities must have shape (n_samples, 2)
    assert probs.shape == (len(dummy_inference_batch), 2)
    # Range check
    assert (probs >= 0.0).all()
    assert (probs <= 1.0).all()
    # Row probabilities sum to 1.0
    np.testing.assert_allclose(probs.sum(axis=1), np.ones(len(dummy_inference_batch)), rtol=1e-5)


def test_model_inference_determinism(loaded_rf_pipeline, dummy_inference_batch):
    probs1 = loaded_rf_pipeline.predict_proba(dummy_inference_batch)[:, 1]
    probs2 = loaded_rf_pipeline.predict_proba(dummy_inference_batch)[:, 1]
    np.testing.assert_array_equal(probs1, probs2)


def test_classification_threshold_application(loaded_rf_pipeline, dummy_inference_batch, model_sidecar):
    threshold = model_sidecar["threshold"]  # 0.21
    fraud_probs = loaded_rf_pipeline.predict_proba(dummy_inference_batch)[:, 1]
    predictions = (fraud_probs >= threshold).astype(int)

    assert set(predictions).issubset({0, 1})
    for p, pred in zip(fraud_probs, predictions):
        if p >= threshold:
            assert pred == 1
        else:
            assert pred == 0
