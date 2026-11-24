"""Unit tests for MerchantRiskEncoder and target encoding leakage prevention."""
import json
import tempfile
from pathlib import Path
import numpy as np
import pandas as pd
import pytest

from ml.features import MerchantRiskEncoder


@pytest.fixture
def synthetic_merchant_data():
    """Generates synthetic merchant transactions across train and inference sets."""
    train_df = pd.DataFrame({
        "MerchantID": [10, 10, 10, 20, 20, 30, np.nan],
        "IsFraud": [1, 0, 1, 0, 0, 1, 0],
    })
    inference_df = pd.DataFrame({
        "MerchantID": [10, 20, 999, np.nan],  # 10 is known, 20 is known, 999 is unseen, NaN is missing
    })
    return train_df, inference_df


def test_merchant_risk_encoder_fit(synthetic_merchant_data):
    train_df, _ = synthetic_merchant_data
    encoder = MerchantRiskEncoder()
    encoder.fit(train_df)

    assert encoder.is_fitted_ is True
    # Total fraud in train: 3/7
    assert pytest.approx(encoder.global_rate_, 1e-4) == 3 / 7

    # Merchant 10: 2 fraud out of 3 -> rate 2/3
    assert pytest.approx(encoder.merchant_rates_["10"], 1e-4) == 2 / 3
    # Merchant 20: 0 fraud out of 2 -> rate 0.0
    assert pytest.approx(encoder.merchant_rates_["20"], 1e-4) == 0.0
    # Merchant 30: 1 fraud out of 1 -> rate 1.0
    assert pytest.approx(encoder.merchant_rates_["30"], 1e-4) == 1.0


def test_training_leave_one_out_transformation(synthetic_merchant_data):
    train_df, _ = synthetic_merchant_data
    encoder = MerchantRiskEncoder()
    encoder.fit(train_df)

    train_rates = encoder.transform(train_df, is_train=True)
    assert len(train_rates) == len(train_df)

    # For merchant 10 (count=3, sum=2):
    # Row 0 (fraud=1): (2 - 1) / (3 - 1) = 1/2 = 0.5
    assert pytest.approx(train_rates.iloc[0], 1e-4) == 0.5
    # Row 1 (fraud=0): (2 - 0) / (3 - 1) = 2/2 = 1.0
    assert pytest.approx(train_rates.iloc[1], 1e-4) == 1.0
    # Row 2 (fraud=1): (2 - 1) / (3 - 1) = 1/2 = 0.5
    assert pytest.approx(train_rates.iloc[2], 1e-4) == 0.5

    # Merchant 30 has count=1: denom <= 0 -> fallback to global rate
    assert pytest.approx(train_rates.iloc[5], 1e-4) == 3 / 7

    # Missing merchant (Row 6) -> fallback to global rate
    assert pytest.approx(train_rates.iloc[6], 1e-4) == 3 / 7


def test_inference_transform_without_labels(synthetic_merchant_data):
    train_df, inference_df = synthetic_merchant_data
    encoder = MerchantRiskEncoder()
    encoder.fit(train_df)

    # Transform without IsFraud in dataframe
    assert "IsFraud" not in inference_df.columns
    inf_rates = encoder.transform(inference_df, is_train=False)

    assert len(inf_rates) == len(inference_df)
    # Known Merchant 10: 2/3
    assert pytest.approx(inf_rates.iloc[0], 1e-4) == 2 / 3
    # Known Merchant 20: 0.0
    assert pytest.approx(inf_rates.iloc[1], 1e-4) == 0.0
    # Unseen Merchant 999: fallback to global rate
    assert pytest.approx(inf_rates.iloc[2], 1e-4) == 3 / 7
    # Missing Merchant (NaN): fallback to global rate
    assert pytest.approx(inf_rates.iloc[3], 1e-4) == 3 / 7


def test_encoder_serialization_roundtrip(synthetic_merchant_data):
    train_df, inference_df = synthetic_merchant_data
    encoder = MerchantRiskEncoder()
    encoder.fit(train_df)

    with tempfile.TemporaryDirectory() as tmp_dir:
        save_path = Path(tmp_dir) / "merchant_encoder.json"
        encoder.save(save_path)
        assert save_path.exists()

        loaded_encoder = MerchantRiskEncoder.load(save_path)
        assert loaded_encoder.is_fitted_ is True
        assert pytest.approx(loaded_encoder.global_rate_, 1e-4) == encoder.global_rate_

        rates_orig = encoder.transform(inference_df, is_train=False)
        rates_loaded = loaded_encoder.transform(inference_df, is_train=False)
        np.testing.assert_allclose(rates_orig.to_numpy(), rates_loaded.to_numpy())
