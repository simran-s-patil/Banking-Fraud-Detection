
"""Automated tests for transaction retrieval services.

These tests use mock database objects. They do not modify MySQL data.
"""

from datetime import datetime
from decimal import Decimal
from unittest.mock import MagicMock

import pytest

import backend.transaction_service as service


def make_mock_database(monkeypatch, fetchone=None, fetchall=None):
    """Create a pretend database connection and cursor."""

    cursor = MagicMock()
    connection = MagicMock()

    cursor.fetchone.return_value = fetchone
    cursor.fetchall.side_effect = fetchall if fetchall is not None else []

    connection.cursor.return_value = cursor

    monkeypatch.setattr(
        service,
        "get_connection",
        lambda: connection,
    )

    return connection, cursor


# ---------------------------------------------------------
# Tests for get_transaction_by_id()
# ---------------------------------------------------------

def test_get_transaction_by_id_returns_transaction(monkeypatch):
    expected = {
        "TransactionID": 1001,
        "Amount": Decimal("250.00"),
        "Status": "SUCCESS",
    }

    connection, cursor = make_mock_database(
        monkeypatch,
        fetchone=expected,
    )

    result = service.get_transaction_by_id(1001)

    assert result == expected
    cursor.execute.assert_called_once()
    assert cursor.execute.call_args[0][1] == (1001,)
    cursor.close.assert_called_once()
    connection.close.assert_called_once()


def test_get_transaction_by_id_returns_none_when_not_found(monkeypatch):
    connection, cursor = make_mock_database(
        monkeypatch,
        fetchone=None,
    )

    result = service.get_transaction_by_id(999999)

    assert result is None
    cursor.close.assert_called_once()
    connection.close.assert_called_once()


def test_get_transaction_by_id_closes_connection_on_error(monkeypatch):
    connection, cursor = make_mock_database(monkeypatch)
    cursor.execute.side_effect = RuntimeError("Database error")

    with pytest.raises(RuntimeError, match="Database error"):
        service.get_transaction_by_id(1001)

    connection.close.assert_called_once()


# ---------------------------------------------------------
# Tests for get_recent_transactions()
# ---------------------------------------------------------

def test_get_recent_transactions_returns_rows(monkeypatch):
    expected = [
        {"TransactionID": 1002},
        {"TransactionID": 1001},
    ]

    connection, cursor = make_mock_database(
        monkeypatch,
        fetchall=[expected],
    )

    result = service.get_recent_transactions(limit=2)

    assert result == expected
    assert cursor.execute.call_args[0][1] == (2,)
    cursor.close.assert_called_once()
    connection.close.assert_called_once()


def test_get_recent_transactions_uses_default_limit(monkeypatch):
    connection, cursor = make_mock_database(
        monkeypatch,
        fetchall=[[]],
    )

    service.get_recent_transactions()

    assert cursor.execute.call_args[0][1] == (20,)
    connection.close.assert_called_once()


@pytest.mark.parametrize("limit", [0, -1, 501, True, 1.5, "10"])
def test_get_recent_transactions_rejects_invalid_limit(limit):
    with pytest.raises(ValueError):
        service.get_recent_transactions(limit=limit)


# ---------------------------------------------------------
# Tests for get_customer_transaction_history()
# ---------------------------------------------------------

def make_transaction_row(transaction_id, customer_id, timestamp):
    """Create a pretend transaction row for history tests."""

    return {
        "TransactionID": transaction_id,
        "TransactionTimestamp": timestamp,
        "SenderCustomerID": customer_id,
    }


def test_customer_history_returns_target_and_history(monkeypatch):
    timestamp = datetime(2025, 12, 31, 10, 0, 0)

    target = make_transaction_row(1002, 7, timestamp)
    earlier = make_transaction_row(
        1001,
        7,
        datetime(2025, 12, 30, 10, 0, 0),
    )

    connection, cursor = make_mock_database(
        monkeypatch,
        fetchall=[
            [target],
            [earlier],
        ],
    )

    result = service.get_customer_transaction_history([1002])

    assert result["raw_transactions"] == [target]
    assert result["history"] == [earlier]

    assert cursor.execute.call_count == 2
    cursor.close.assert_called_once()
    connection.close.assert_called_once()


def test_customer_history_returns_empty_history(monkeypatch):
    timestamp = datetime(2025, 12, 31, 10, 0, 0)
    target = make_transaction_row(1002, 7, timestamp)

    connection, cursor = make_mock_database(
        monkeypatch,
        fetchall=[
            [target],
            [],
        ],
    )

    result = service.get_customer_transaction_history([1002])

    assert result["raw_transactions"] == [target]
    assert result["history"] == []
    connection.close.assert_called_once()


def test_customer_history_rejects_non_list_input():
    with pytest.raises(ValueError):
        service.get_customer_transaction_history(1001)


def test_customer_history_rejects_empty_input():
    with pytest.raises(ValueError):
        service.get_customer_transaction_history([])


@pytest.mark.parametrize(
    "transaction_ids",
    [
        [0],
        [-1],
        [True],
        ["1001"],
        [1001, "1002"],
    ],
)
def test_customer_history_rejects_invalid_ids(transaction_ids):
    with pytest.raises(ValueError):
        service.get_customer_transaction_history(transaction_ids)


def test_customer_history_rejects_duplicate_ids():
    with pytest.raises(ValueError):
        service.get_customer_transaction_history([1001, 1001])


def test_customer_history_rejects_missing_transaction(monkeypatch):
    connection, cursor = make_mock_database(
        monkeypatch,
        fetchall=[[]],
    )

    with pytest.raises(ValueError, match="Transaction IDs not found"):
        service.get_customer_transaction_history([999999])

    connection.close.assert_called_once()
