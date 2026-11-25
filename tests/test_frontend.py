"""Unit tests for Frontend Utilities, Charts, and Components."""
import pandas as pd
import pytest

from streamlit_app.components.charts import (
    plot_amount_distribution,
    plot_risk_distribution,
    plot_shap_contributions,
    plot_transaction_volume,
)
from streamlit_app.components.fraud_analysis import generate_natural_language_explanation
from streamlit_app.utils.formatting import (
    format_currency,
    format_probability,
    format_timestamp,
    get_prediction_badge_html,
    get_risk_badge_html,
)
from streamlit_app.utils.validation import validate_customer_id, validate_transaction_id


def test_formatting_currency():
    """Verify currency representation."""
    assert format_currency(45000.5) == "₹45,000.50"
    assert format_currency(0) == "₹0.00"
    assert format_currency(None) == "N/A"


def test_formatting_probability():
    """Verify fraud probability formatting."""
    assert format_probability(0.6267) == "62.67%"
    assert format_probability(0.0) == "0.00%"
    assert format_probability(None) == "N/A"


def test_formatting_badges():
    """Verify HTML badges for risk status and prediction."""
    low_badge = get_risk_badge_html("LOW")
    assert "LOW" in low_badge
    assert "#28a745" in low_badge

    high_badge = get_risk_badge_html("HIGH")
    assert "HIGH" in high_badge
    assert "#dc3545" in high_badge

    pred_legit = get_prediction_badge_html("LEGITIMATE")
    assert "LEGITIMATE" in pred_legit

    pred_fraud = get_prediction_badge_html("FRAUDULENT")
    assert "FRAUDULENT" in pred_fraud


def test_validation_customer_id():
    """Verify customer ID validation rules."""
    valid, cid, err = validate_customer_id("501")
    assert valid is True
    assert cid == 501
    assert err is None

    valid, cid, err = validate_customer_id("-5")
    assert valid is False
    assert "positive integer" in err

    valid, cid, err = validate_customer_id("abc")
    assert valid is False
    assert "Invalid customer ID" in err

    valid, cid, err = validate_customer_id("")
    assert valid is False


def test_validation_transaction_id():
    """Verify transaction ID validation rules."""
    valid, tid, err = validate_transaction_id(17)
    assert valid is True
    assert tid == 17

    valid, tid, err = validate_transaction_id("0")
    assert valid is False

    valid, tid, err = validate_transaction_id(None)
    assert valid is False


def test_chart_generation():
    """Verify Plotly figure creation without errors."""
    # 1. SHAP chart
    reasons = [
        {"feature": "amount", "contribution": 0.15, "direction": "INCREASES_RISK"},
        {"feature": "sender_account_age_days", "contribution": -0.08, "direction": "DECREASES_RISK"},
    ]
    fig_shap = plot_shap_contributions(reasons)
    assert fig_shap is not None
    assert len(fig_shap.data) == 1

    # 2. Risk distribution
    counts = {"LOW": 100, "MEDIUM": 20, "HIGH": 5}
    fig_risk = plot_risk_distribution(counts)
    assert fig_risk is not None

    # 3. Transaction volume
    df_vol = pd.DataFrame([
        {"timestamp": "2025-03-01 10:00:00"},
        {"timestamp": "2025-03-01 11:00:00"},
        {"timestamp": "2025-03-02 10:00:00"},
    ])
    fig_vol = plot_transaction_volume(df_vol)
    assert fig_vol is not None

    # 4. Amount distribution
    fig_amt = plot_amount_distribution([100.0, 500.0, 1500.0, 50000.0])
    assert fig_amt is not None


def test_natural_language_explanation_generation():
    """Verify dynamic narrative generation for fraud vs legitimate outcomes."""
    reasons = [
        {"feature": "amount", "contribution": 0.1674, "direction": "INCREASES_RISK"},
        {"feature": "hour_of_day", "contribution": -0.0321, "direction": "DECREASES_RISK"},
    ]

    # Fraudulent case (prob >= 0.21)
    fraud_narrative = generate_natural_language_explanation(reasons, prob=0.6267)
    assert "high risk" in fraud_narrative.lower()
    assert "Transaction amount" in fraud_narrative
    assert "not constitute legal causality" in fraud_narrative

    # Legitimate case (prob < 0.21)
    legit_narrative = generate_natural_language_explanation(reasons, prob=0.0333)
    assert "low risk" in legit_narrative.lower()
    assert "not constitute legal causality" in legit_narrative
