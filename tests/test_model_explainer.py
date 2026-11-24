"""Unit and integration tests for SHAP model explainability (ml/model_explainer.py)."""
import pandas as pd
import pytest

from ml.config import DEFAULT_MODEL_PATH, EXPECTED_FEATURE_COLUMNS, POSITIVE_CLASS_INDEX
from ml.model_explainer import ModelExplainer, explain_transaction


@pytest.fixture
def sample_feature_record() -> dict:
    """Creates a valid 30-feature dictionary matching EXPECTED_FEATURE_COLUMNS."""
    features = {
        "amount": 5000.0,
        "amount_log": 8.5174,
        "amount_zscore_sender": 0.5,
        "hour_of_day": 14,
        "day_of_week": 2,
        "is_night": 0,
        "is_festival_day": 0,
        "sender_account_age_days": 180,
        "has_sender_history": 1,
        "sender_txn_count_10m": 1,
        "sender_txn_count_60m": 2,
        "sender_txn_count_1440m": 3,
        "sender_amount_sum_60m": 6000.0,
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
    return features


def test_explainer_initialization():
    """Verify that ModelExplainer loads production pipeline and initializes TreeExplainer."""
    explainer = ModelExplainer()
    assert explainer.pipeline is not None
    assert explainer.preprocessor is not None
    assert explainer.model is not None
    assert explainer.explainer is not None
    assert len(explainer.preprocessed_feature_names) == 46


def test_positive_class_index():
    """Confirm positive class index is 1 (Fraudulent)."""
    assert POSITIVE_CLASS_INDEX == 1


def test_single_transaction_explanation_schema(sample_feature_record):
    """Verify structured explanation schema for an individual transaction."""
    result = explain_transaction(sample_feature_record, top_k=5)

    assert "top_reasons" in result
    assert "base_value" in result
    assert "fraud_probability" in result

    assert isinstance(result["base_value"], float)
    assert 0.0 <= result["base_value"] <= 1.0
    assert isinstance(result["fraud_probability"], float)
    assert 0.0 <= result["fraud_probability"] <= 1.0

    reasons = result["top_reasons"]
    assert len(reasons) <= 5

    for item in reasons:
        assert "feature" in item
        assert "contribution" in item
        assert "direction" in item
        assert isinstance(item["feature"], str)
        assert isinstance(item["contribution"], float)
        assert item["direction"] in ("INCREASES_RISK", "DECREASES_RISK")
        if item["contribution"] > 0:
            assert item["direction"] == "INCREASES_RISK"
        else:
            assert item["direction"] == "DECREASES_RISK"


def test_custom_top_k(sample_feature_record):
    """Verify top_k parameter limits the number of returned reasons."""
    res_3 = explain_transaction(sample_feature_record, top_k=3)
    assert len(res_3["top_reasons"]) == 3

    res_1 = explain_transaction(sample_feature_record, top_k=1)
    assert len(res_1["top_reasons"]) == 1


def test_missing_features_raises_error(sample_feature_record):
    """Verify that missing feature columns raise ValueError."""
    corrupted = sample_feature_record.copy()
    del corrupted["amount"]
    with pytest.raises(ValueError, match="Missing required feature columns"):
        explain_transaction(corrupted)


def test_multi_row_dataframe_raises_error(sample_feature_record):
    """Verify that passing multiple rows to explain_transaction raises ValueError."""
    df_two_rows = pd.DataFrame([sample_feature_record, sample_feature_record])
    with pytest.raises(ValueError, match="expects exactly 1 row"):
        explain_transaction(df_two_rows)
