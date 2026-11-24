
"""Automated tests for fraud scoring validation."""

import pytest
from decimal import Decimal

from backend.scoring_service import (
    validate_scoring_result,
    validate_scoring_batch,
)


def valid_result():
    """Return a sample valid prediction result."""
    return {
        "transaction_id": 1001,
        "fraud_probability": 0.85,
        "prediction": "FRAUDULENT",
        "model_version": "RF_v1",
    }


def test_valid_scoring_result():
    result = validate_scoring_result(valid_result())

    assert result["transaction_id"] == 1001
    assert result["fraud_probability"] == Decimal("0.85")
    assert result["prediction"] == "FRAUDULENT"
    assert result["model_version"] == "RF_v1"


def test_model_version_whitespace_is_removed():
    data = valid_result()
    data["model_version"] = "  RF_v1  "

    result = validate_scoring_result(data)

    assert result["model_version"] == "RF_v1"


@pytest.mark.parametrize("probability", [-0.1, 1.1, "nan", "inf", "invalid"])
def test_invalid_fraud_probability(probability):
    data = valid_result()
    data["fraud_probability"] = probability

    with pytest.raises(ValueError):
        validate_scoring_result(data)


@pytest.mark.parametrize("prediction", ["MAYBE", "FRAUD", "", None])
def test_invalid_prediction(prediction):
    data = valid_result()
    data["prediction"] = prediction

    with pytest.raises(ValueError):
        validate_scoring_result(data)


@pytest.mark.parametrize("transaction_id", [0, -1, True, "1001"])
def test_invalid_transaction_id(transaction_id):
    data = valid_result()
    data["transaction_id"] = transaction_id

    with pytest.raises(ValueError):
        validate_scoring_result(data)


def test_missing_required_field():
    data = valid_result()
    del data["prediction"]

    with pytest.raises(ValueError):
        validate_scoring_result(data)


def test_empty_model_version():
    data = valid_result()
    data["model_version"] = "   "

    with pytest.raises(ValueError):
        validate_scoring_result(data)


def test_valid_scoring_batch():
    results = [
        valid_result(),
        {
            "transaction_id": 1002,
            "fraud_probability": 0.15,
            "prediction": "LEGITIMATE",
            "model_version": "RF_v1",
        },
    ]

    validated = validate_scoring_batch(results)

    assert len(validated) == 2
    assert validated[0]["transaction_id"] == 1001
    assert validated[1]["transaction_id"] == 1002


def test_empty_scoring_batch():
    with pytest.raises(ValueError):
        validate_scoring_batch([])


def test_non_list_scoring_batch():
    with pytest.raises(ValueError):
        validate_scoring_batch("not a list")


def test_duplicate_transaction_ids():
    results = [valid_result(), valid_result()]

    with pytest.raises(ValueError, match="Duplicate transaction ID"):
        validate_scoring_batch(results)


def test_invalid_item_rejects_entire_batch():
    first = valid_result()
    second = valid_result()
    second["transaction_id"] = 1002
    second["fraud_probability"] = 1.5

    with pytest.raises(ValueError):
        validate_scoring_batch([first, second])
