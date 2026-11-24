
"""Automated tests for fraud alert services."""

import pytest

from backend.alert_service import (
    create_alert,
    get_alert_by_id,
    get_alerts,
    update_alert_review_status,
)


@pytest.mark.parametrize("alert_id", [0, -1, True, "1"])
def test_invalid_alert_id(alert_id):
    with pytest.raises(ValueError):
        get_alert_by_id(alert_id)


@pytest.mark.parametrize("limit", [0, -1, 501, True, 1.5])
def test_invalid_alert_limit(limit):
    with pytest.raises(ValueError):
        get_alerts(limit=limit)


def test_invalid_review_status_filter():
    with pytest.raises(ValueError):
        get_alerts(review_status="MAYBE")


@pytest.mark.parametrize(
    "score",
    [-0.1, 1.1, "nan", "inf", "invalid"],
)
def test_invalid_alert_score(score):
    with pytest.raises(ValueError):
        create_alert(20000, score, "Test alert")


@pytest.mark.parametrize("reason", ["", "   ", None, 123])
def test_invalid_alert_reason(reason):
    with pytest.raises(ValueError):
        create_alert(20000, 0.5, reason)


def test_alert_reason_too_long():
    with pytest.raises(ValueError):
        create_alert(20000, 0.5, "A" * 256)


def test_create_alert_rejects_invalid_transaction_id():
    with pytest.raises(ValueError):
        create_alert(-1, 0.5, "Test alert")


def test_update_rejects_invalid_status():
    with pytest.raises(ValueError):
        update_alert_review_status(1, "MAYBE")


def test_update_rejects_invalid_alert_id():
    with pytest.raises(ValueError):
        update_alert_review_status(-1, "OPEN")
