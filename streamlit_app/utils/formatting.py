"""UI Formatting Utilities for Currencies, Dates, and Risk Status Badges."""
from typing import Any

from streamlit_app.config import (
    COLOR_FRAUDULENT,
    COLOR_LEGITIMATE,
    COLOR_RISK_HIGH,
    COLOR_RISK_LOW,
    COLOR_RISK_MEDIUM,
)


def format_currency(amount: float | int | None) -> str:
    """Format numeric amount into Indian Rupee representation (e.g. ₹45,000.00)."""
    if amount is None:
        return "N/A"
    try:
        val = float(amount)
        return f"₹{val:,.2f}"
    except (ValueError, TypeError):
        return str(amount)


def format_probability(prob: float | None) -> str:
    """Format fraud probability into percentage string."""
    if prob is None:
        return "N/A"
    try:
        val = float(prob)
        return f"{val * 100:.2f}%"
    except (ValueError, TypeError):
        return str(prob)


def get_risk_badge_html(risk_status: str | None) -> str:
    """Return colored HTML badge for operational risk status."""
    if not risk_status:
        return '<span style="color: gray;">UNKNOWN</span>'

    status = str(risk_status).upper()
    if status == "LOW":
        color = COLOR_RISK_LOW
        bg = "#e8f5e9"
    elif status == "MEDIUM":
        color = COLOR_RISK_MEDIUM
        bg = "#fff3e0"
    elif status == "HIGH":
        color = COLOR_RISK_HIGH
        bg = "#ffebee"
    else:
        color = "#6c757d"
        bg = "#f8f9fa"

    return (
        f'<span style="background-color: {bg}; color: {color}; font-weight: 700; '
        f'padding: 3px 8px; border-radius: 4px; border: 1px solid {color}33;">{status}</span>'
    )


def get_prediction_badge_html(prediction: str | None) -> str:
    """Return colored HTML badge for binary classification prediction."""
    if not prediction:
        return '<span style="color: gray;">UNKNOWN</span>'

    pred = str(prediction).upper()
    if pred == "LEGITIMATE":
        color = COLOR_LEGITIMATE
        bg = "#e8f5e9"
    elif pred == "FRAUDULENT":
        color = COLOR_FRAUDULENT
        bg = "#ffebee"
    else:
        color = "#6c757d"
        bg = "#f8f9fa"

    return (
        f'<span style="background-color: {bg}; color: {color}; font-weight: 700; '
        f'padding: 3px 8px; border-radius: 4px; border: 1px solid {color}33;">{pred}</span>'
    )


def format_timestamp(ts: Any) -> str:
    """Format timestamps to clean readable display."""
    if not ts:
        return "N/A"
    return str(ts).replace("T", " ")[:19]
