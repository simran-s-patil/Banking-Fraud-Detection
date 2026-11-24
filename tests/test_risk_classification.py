"""Unit tests for operational risk classification and thresholding (ml/config.py)."""
import pytest

from ml.config import (
    CLASSIFICATION_THRESHOLD,
    PRED_FRAUDULENT,
    PRED_LEGITIMATE,
    RISK_HIGH,
    RISK_LOW,
    RISK_MEDIUM,
    classify_prediction,
    classify_risk,
)


def test_classify_risk_exact_boundaries():
    """Verify operational risk bands on required boundary values."""
    # LOW band: [0.00, 0.10)
    assert classify_risk(0.00) == RISK_LOW
    assert classify_risk(0.05) == RISK_LOW
    assert classify_risk(0.0999) == RISK_LOW

    # MEDIUM band: [0.10, 0.21)
    assert classify_risk(0.10) == RISK_MEDIUM
    assert classify_risk(0.15) == RISK_MEDIUM
    assert classify_risk(0.2099) == RISK_MEDIUM

    # HIGH band: [0.21, 1.00]
    assert classify_risk(0.21) == RISK_HIGH
    assert classify_risk(0.50) == RISK_HIGH
    assert classify_risk(0.9999) == RISK_HIGH
    assert classify_risk(1.00) == RISK_HIGH


def test_classify_risk_out_of_bounds():
    """Verify that probabilities below 0.0 or above 1.0 raise ValueError."""
    with pytest.raises(ValueError, match=r"within \[0.0, 1.0\]"):
        classify_risk(-0.01)

    with pytest.raises(ValueError, match=r"within \[0.0, 1.0\]"):
        classify_risk(-1.0)

    with pytest.raises(ValueError, match=r"within \[0.0, 1.0\]"):
        classify_risk(1.01)

    with pytest.raises(ValueError, match=r"within \[0.0, 1.0\]"):
        classify_risk(2.5)


def test_classify_risk_invalid_types():
    """Verify that None and non-numeric inputs raise ValueError."""
    with pytest.raises(ValueError):
        classify_risk(None)

    with pytest.raises(ValueError):
        classify_risk("not_a_number")


def test_classify_prediction_boundaries():
    """Verify binary classification behavior at the 0.21 decision threshold."""
    assert classify_prediction(0.00) == PRED_LEGITIMATE
    assert classify_prediction(0.2099) == PRED_LEGITIMATE
    assert classify_prediction(0.2100) == PRED_FRAUDULENT
    assert classify_prediction(0.2101) == PRED_FRAUDULENT
    assert classify_prediction(1.00) == PRED_FRAUDULENT


def test_custom_threshold_override():
    """Verify classification with custom threshold override."""
    assert classify_prediction(0.15, threshold=0.10) == PRED_FRAUDULENT
    assert classify_prediction(0.15, threshold=0.50) == PRED_LEGITIMATE
