"""Unit tests for ML preprocessing pipeline (ml/train.py:build_preprocessor)."""
import numpy as np
import pandas as pd
import pytest
from sklearn.compose import ColumnTransformer

from ml.features import ALL_NUMERIC_FEATURES, CATEGORICAL_FEATURES
from ml.train import build_preprocessor


@pytest.fixture
def dummy_train_and_test_data():
    """Generates synthetic train and test DataFrames matching feature column specifications."""
    np.random.seed(42)
    n_train, n_test = 50, 10

    def make_df(n):
        data = {}
        for col in ALL_NUMERIC_FEATURES:
            data[col] = np.random.uniform(0, 100, size=n)
        data["sender_account_type"] = np.random.choice(["Savings", "Current"], size=n)
        data["receiver_shape"] = np.random.choice(
            ["account_only", "external_upi_only", "account_and_upi", "NOT_APPLICABLE"], size=n
        )
        data["merchant_category"] = np.random.choice(["Electronics", "Gaming", "Jewellery"], size=n)
        return pd.DataFrame(data)

    df_train = make_df(n_train)
    df_test = make_df(n_test)

    # Introduce NaNs to test imputer robustness
    df_train.loc[0, "amount"] = np.nan
    df_train.loc[1, "sender_account_type"] = None
    df_test.loc[0, "merchant_risk_rate"] = np.nan
    df_test.loc[1, "merchant_category"] = None
    # Introduce unseen category in test
    df_test.loc[2, "merchant_category"] = "UNSEEN_SUPERMARKET"

    return df_train, df_test


def test_build_preprocessor_structure():
    preprocessor = build_preprocessor(ALL_NUMERIC_FEATURES)
    assert isinstance(preprocessor, ColumnTransformer)
    transformer_names = [name for name, _, _ in preprocessor.transformers]
    assert "numeric" in transformer_names
    assert "categorical" in transformer_names


def test_preprocessor_fit_transform(dummy_train_and_test_data):
    df_train, df_test = dummy_train_and_test_data
    feature_cols = ALL_NUMERIC_FEATURES + CATEGORICAL_FEATURES

    preprocessor = build_preprocessor(ALL_NUMERIC_FEATURES)
    X_train_proc = preprocessor.fit_transform(df_train[feature_cols])

    # Check transformed train matrix
    assert isinstance(X_train_proc, np.ndarray)
    assert not np.isnan(X_train_proc).any(), "Preprocessed training matrix contains NaNs"
    assert X_train_proc.shape[0] == len(df_train)

    # Transform test set without refitting
    X_test_proc = preprocessor.transform(df_test[feature_cols])
    assert isinstance(X_test_proc, np.ndarray)
    assert not np.isnan(X_test_proc).any(), "Preprocessed test matrix contains NaNs"
    assert X_test_proc.shape[0] == len(df_test)
    assert X_test_proc.shape[1] == X_train_proc.shape[1], "Feature dimension mismatch between train and test"


def test_handle_unknown_and_missing_categories(dummy_train_and_test_data):
    df_train, df_test = dummy_train_and_test_data
    feature_cols = ALL_NUMERIC_FEATURES + CATEGORICAL_FEATURES

    preprocessor = build_preprocessor(ALL_NUMERIC_FEATURES)
    preprocessor.fit(df_train[feature_cols])

    # Row with NaN category and unseen category should transform without raising exception
    X_test_proc = preprocessor.transform(df_test[feature_cols])
    assert X_test_proc.shape[0] == len(df_test)
    assert not np.isnan(X_test_proc).any()
