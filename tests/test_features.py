"""Unit tests for feature engineering transformations (ml/features.py)."""
import numpy as np
import pandas as pd
import pytest

from ml.features import (
    ALL_NUMERIC_FEATURES,
    CATEGORICAL_FEATURES,
    HIGH_RISK_CATEGORIES,
    NIGHT_HOURS,
    NUMERIC_FEATURES,
    build_features,
)


@pytest.fixture
def sample_raw_transactions() -> pd.DataFrame:
    """Creates a minimal synthetic transaction DataFrame for testing feature engineering."""
    base_time = pd.Timestamp("2025-03-01 10:00:00")
    return pd.DataFrame([
        {
            "TransactionID": 1,
            "TransactionTimestamp": base_time,
            "Amount": 1500.0,
            "SenderAccountNumber": 10001,
            "ReceiverAccountNumber": 10002,
            "ReceiverUPIID": None,
            "TransactionTypeName": "P2P_UPI",
            "MerchantID": None,
            "MerchantCategory": None,
            "DeviceID": None,
            "IPAddress": None,
            "Location": None,
            "CardReferenceToken": None,
            "SenderCustomerID": 501,
            "SenderAccountType": "Savings",
            "SenderAccountCreatedAt": pd.Timestamp("2024-01-01 00:00:00"),
            "IsFraud": 0,
            "Scenario": "normal",
            "Pattern": "normal",
        },
        {
            "TransactionID": 2,
            "TransactionTimestamp": base_time + pd.Timedelta("5min"),
            "Amount": 50.0,
            "SenderAccountNumber": 10001,
            "ReceiverAccountNumber": None,
            "ReceiverUPIID": "merchant@synthupi",
            "TransactionTypeName": "P2P_UPI",
            "MerchantID": None,
            "MerchantCategory": None,
            "DeviceID": None,
            "IPAddress": None,
            "Location": None,
            "CardReferenceToken": None,
            "SenderCustomerID": 501,
            "SenderAccountType": "Savings",
            "SenderAccountCreatedAt": pd.Timestamp("2024-01-01 00:00:00"),
            "IsFraud": 0,
            "Scenario": "normal",
            "Pattern": "normal",
        },
        {
            "TransactionID": 3,
            "TransactionTimestamp": base_time + pd.Timedelta("15min"),
            "Amount": 25000.0,
            "SenderAccountNumber": 10003,
            "ReceiverAccountNumber": None,
            "ReceiverUPIID": None,
            "TransactionTypeName": "CNP_ECOM",
            "MerchantID": 11,
            "MerchantCategory": "Electronics",
            "DeviceID": "dev_abc123",
            "IPAddress": "192.0.2.10",
            "Location": "Bengaluru, Karnataka",
            "CardReferenceToken": "tok_xyz",
            "SenderCustomerID": 502,
            "SenderAccountType": "Current",
            "SenderAccountCreatedAt": pd.Timestamp("2024-06-01 00:00:00"),
            "IsFraud": 1,
            "Scenario": "fraud",
            "Pattern": "high_amount",
        },
        {
            "TransactionID": 4,
            "TransactionTimestamp": base_time + pd.Timedelta("25min"),
            "Amount": 1200.0,
            "SenderAccountNumber": 10003,
            "ReceiverAccountNumber": None,
            "ReceiverUPIID": None,
            "TransactionTypeName": "CNP_ECOM",
            "MerchantID": 11,
            "MerchantCategory": "Electronics",
            "DeviceID": "dev_new999",
            "IPAddress": "203.0.113.5",
            "Location": "Mumbai, Maharashtra",
            "CardReferenceToken": "tok_xyz",
            "SenderCustomerID": 502,
            "SenderAccountType": "Current",
            "SenderAccountCreatedAt": pd.Timestamp("2024-06-01 00:00:00"),
            "IsFraud": 0,
            "Scenario": "normal",
            "Pattern": "normal",
        },
    ])


def test_build_features_output_columns(sample_raw_transactions):
    features = build_features(sample_raw_transactions)
    expected_feature_cols = NUMERIC_FEATURES + CATEGORICAL_FEATURES
    for col in expected_feature_cols:
        assert col in features.columns, f"Missing expected feature column '{col}'"

    # Metadata and target columns retained
    for meta_col in ["TransactionID", "TransactionTimestamp", "IsFraud", "Scenario", "Pattern"]:
        assert meta_col in features.columns


def test_amount_transformations(sample_raw_transactions):
    features = build_features(sample_raw_transactions)
    # Check amount log is np.log1p(amount)
    np.testing.assert_allclose(
        features["amount_log"].to_numpy(),
        np.log1p(features["amount"].to_numpy()),
        rtol=1e-5,
    )
    assert (features["amount"] > 0).all()


def test_calendar_and_temporal_features(sample_raw_transactions):
    features = build_features(sample_raw_transactions)
    assert features["hour_of_day"].between(0, 23).all()
    assert features["day_of_week"].between(0, 6).all()
    assert set(features["is_night"].unique()).issubset({0, 1})
    assert set(features["is_festival_day"].unique()).issubset({0, 1})

    # Verify night hour definition
    for _, row in features.iterrows():
        expected_night = 1 if row["hour_of_day"] in NIGHT_HOURS else 0
        assert row["is_night"] == expected_night


def test_sender_account_age(sample_raw_transactions):
    features = build_features(sample_raw_transactions)
    # Txn 1: 2025-03-01 - 2024-01-01 = 425 days
    assert features.loc[features["TransactionID"] == 1, "sender_account_age_days"].iloc[0] == 425
    assert (features["sender_account_age_days"] >= 0).all()


def test_p2p_channel_invariants(sample_raw_transactions):
    features = build_features(sample_raw_transactions)
    p2p_rows = features[features["is_p2p"] == 1]
    assert len(p2p_rows) == 2

    # P2P rows should have receiver_shape defined and CNP-specific indicators as 0
    assert set(p2p_rows["receiver_shape"]).issubset({"account_only", "external_upi_only", "account_and_upi"})
    assert (p2p_rows["has_device_id"] == 0).all()
    assert (p2p_rows["has_card_token"] == 0).all()
    assert (p2p_rows["is_high_risk_category"] == 0).all()


def test_cnp_channel_invariants_and_device_changes(sample_raw_transactions):
    features = build_features(sample_raw_transactions)
    cnp_rows = features[features["is_p2p"] == 0]
    assert len(cnp_rows) == 2

    # First CNP txn for sender 10003
    first_cnp = cnp_rows[cnp_rows["TransactionID"] == 3].iloc[0]
    assert first_cnp["has_device_history"] == 0
    assert first_cnp["device_changed_for_account"] == 0

    # Second CNP txn for sender 10003 had new device dev_new999
    second_cnp = cnp_rows[cnp_rows["TransactionID"] == 4].iloc[0]
    assert second_cnp["has_device_history"] == 1
    assert second_cnp["device_changed_for_account"] == 1
    assert second_cnp["location_changed_for_account"] == 1


def test_velocity_rolling_prior_window(sample_raw_transactions):
    features = build_features(sample_raw_transactions)
    # First txn for sender 10001 (Txn 1): prior counts must be 0
    row1 = features[features["TransactionID"] == 1].iloc[0]
    assert row1["sender_txn_count_10m"] == 0
    assert row1["has_sender_history"] == 0

    # Second txn for sender 10001 (Txn 2, 5 mins later): prior count in 10m is 1
    row2 = features[features["TransactionID"] == 2].iloc[0]
    assert row2["sender_txn_count_10m"] == 1
    assert row2["has_sender_history"] == 1
