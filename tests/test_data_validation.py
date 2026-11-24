"""Unit tests for raw transaction data validation and schema integrity."""
import numpy as np
import pandas as pd
import pytest


def validate_raw_transaction_batch(df: pd.DataFrame) -> list[str]:
    """Validates raw transaction batch against required schema invariants.

    Returns a list of error strings. Empty list indicates valid batch.
    """
    errors = []
    mandatory_cols = ["TransactionID", "TransactionTimestamp", "Amount", "SenderAccountNumber", "TransactionTypeName"]
    for col in mandatory_cols:
        if col not in df.columns:
            errors.append(f"Missing mandatory column: '{col}'")
        elif df[col].isna().any():
            errors.append(f"Column '{col}' contains NULL values")

    if "Amount" in df.columns:
        if not pd.api.types.is_numeric_dtype(df["Amount"]):
            errors.append("Column 'Amount' must be numeric")
        elif (df["Amount"] <= 0).any():
            errors.append("Column 'Amount' contains zero or negative values")

    if "TransactionID" in df.columns:
        if df["TransactionID"].duplicated().any():
            errors.append("Duplicate TransactionID detected")

    if "TransactionTypeName" in df.columns:
        invalid_types = set(df["TransactionTypeName"].dropna().unique()) - {"P2P_UPI", "CNP_ECOM"}
        if invalid_types:
            errors.append(f"Invalid TransactionTypeName: {invalid_types}")

    return errors


def test_valid_transaction_batch():
    valid_df = pd.DataFrame([
        {
            "TransactionID": 1,
            "TransactionTimestamp": "2025-01-01 10:00:00",
            "Amount": 100.50,
            "SenderAccountNumber": 10001,
            "TransactionTypeName": "P2P_UPI",
        },
        {
            "TransactionID": 2,
            "TransactionTimestamp": "2025-01-01 10:05:00",
            "Amount": 500.00,
            "SenderAccountNumber": 10002,
            "TransactionTypeName": "CNP_ECOM",
        },
    ])
    errors = validate_raw_transaction_batch(valid_df)
    assert errors == []


def test_detect_missing_mandatory_fields():
    df = pd.DataFrame([
        {"TransactionID": 1, "Amount": 100.0, "TransactionTypeName": "P2P_UPI"}
    ])
    errors = validate_raw_transaction_batch(df)
    assert any("TransactionTimestamp" in e for e in errors)
    assert any("SenderAccountNumber" in e for e in errors)


def test_detect_invalid_amount_zero_or_negative():
    df = pd.DataFrame([
        {
            "TransactionID": 1,
            "TransactionTimestamp": "2025-01-01 10:00:00",
            "Amount": -50.00,
            "SenderAccountNumber": 10001,
            "TransactionTypeName": "P2P_UPI",
        },
        {
            "TransactionID": 2,
            "TransactionTimestamp": "2025-01-01 10:01:00",
            "Amount": 0.00,
            "SenderAccountNumber": 10002,
            "TransactionTypeName": "CNP_ECOM",
        },
    ])
    errors = validate_raw_transaction_batch(df)
    assert any("zero or negative" in e for e in errors)


def test_detect_duplicate_transaction_id():
    df = pd.DataFrame([
        {
            "TransactionID": 101,
            "TransactionTimestamp": "2025-01-01 10:00:00",
            "Amount": 200.0,
            "SenderAccountNumber": 10001,
            "TransactionTypeName": "P2P_UPI",
        },
        {
            "TransactionID": 101,  # Duplicate
            "TransactionTimestamp": "2025-01-01 10:02:00",
            "Amount": 300.0,
            "SenderAccountNumber": 10001,
            "TransactionTypeName": "P2P_UPI",
        },
    ])
    errors = validate_raw_transaction_batch(df)
    assert any("Duplicate TransactionID" in e for e in errors)


def test_detect_invalid_transaction_type():
    df = pd.DataFrame([
        {
            "TransactionID": 1,
            "TransactionTimestamp": "2025-01-01 10:00:00",
            "Amount": 100.0,
            "SenderAccountNumber": 10001,
            "TransactionTypeName": "ATM_WITHDRAWAL",  # Invalid
        }
    ])
    errors = validate_raw_transaction_batch(df)
    assert any("Invalid TransactionTypeName" in e for e in errors)
