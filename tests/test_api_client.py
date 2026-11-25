"""Unit tests for Backend API Client (streamlit_app/api_client.py)."""
from unittest.mock import MagicMock, patch
import pytest
import requests

from streamlit_app.api_client import APIResponse, BackendAPIClient


@pytest.fixture
def client() -> BackendAPIClient:
    return BackendAPIClient(base_url="http://mock-backend:8000", timeout=1.0)


def test_api_client_success_response(client):
    """Verify handling of successful 200 JSON responses."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"status": "healthy", "database_connected": True}

    with patch.object(client.session, "request", return_value=mock_resp):
        resp = client.check_health()
        assert resp.success is True
        assert resp.status_code == 200
        assert resp.data["status"] == "healthy"
        assert resp.error is None
        assert resp.is_offline is False


def test_api_client_connection_error(client):
    """Verify graceful handling when backend service is unreachable."""
    with patch.object(client.session, "request", side_effect=requests.exceptions.ConnectionError("Refused")):
        resp = client.check_health()
        assert resp.success is False
        assert resp.is_offline is True
        assert "Cannot connect to backend" in resp.error


def test_api_client_timeout(client):
    """Verify handling when backend request times out."""
    with patch.object(client.session, "request", side_effect=requests.exceptions.Timeout("Timeout")):
        resp = client.get_overview_metrics()
        assert resp.success is False
        assert resp.is_offline is True
        assert "timed out" in resp.error


def test_api_client_http_error(client):
    """Verify handling of HTTP 404/500 errors."""
    mock_resp = MagicMock()
    mock_resp.status_code = 404
    mock_resp.json.return_value = {"error": "Customer not found."}

    with patch.object(client.session, "request", return_value=mock_resp):
        resp = client.get_customer_detail(99999)
        assert resp.success is False
        assert resp.status_code == 404
        assert resp.error == "Customer not found."


def test_api_client_invalid_json(client):
    """Verify handling when backend returns non-JSON content on 200 OK."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.side_effect = ValueError("Invalid JSON")

    with patch.object(client.session, "request", return_value=mock_resp):
        resp = client.get_transactions()
        assert resp.success is False
        assert "invalid non-JSON" in resp.error


def test_api_client_predict_fallback_to_local():
    """Verify fallback to local Phase 2 ML engine when backend is offline."""
    client = BackendAPIClient(base_url="http://offline-backend:8000")

    # Sample transaction dictionary
    sample_txn = {
        "TransactionID": 101,
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

    # Simulate connection error to backend
    with patch.object(client.session, "request", side_effect=requests.exceptions.ConnectionError("Refused")):
        resp = client.predict_transaction(sample_txn, explain=True)
        # Should successfully score via local ML engine
        assert resp.success is True
        assert resp.data is not None
        assert resp.data["transaction_id"] == 101
        assert "fraud_probability" in resp.data
        assert resp.data["model_version"] == "rf_v1.0"
        assert "explanation" in resp.data
