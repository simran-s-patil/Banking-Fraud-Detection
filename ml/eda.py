"""Dataset readiness / EDA checks -- docs/PHASE3_ML_DESIGN.md Section 2.

Usage: python ml/eda.py
"""
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ml.data_extraction import extract  # noqa: E402
from ml.features import build_features  # noqa: E402
from ml.splits import assign_split  # noqa: E402


def main() -> None:
    raw = extract(force=False)
    print(f"Rows extracted: {len(raw)} (expected 20,000)")

    feature_df = build_features(raw)
    print("\nTarget distribution (IsFraud):")
    print(feature_df["IsFraud"].value_counts(normalize=False))
    print(feature_df["IsFraud"].value_counts(normalize=True).round(4))

    print("\nTransaction type mix:")
    print(feature_df["TransactionTypeName"].value_counts())

    split = assign_split(feature_df["TransactionTimestamp"])
    print("\nSplit sizes:", split.value_counts().to_dict())
    print("Fraud rows per split:", feature_df.groupby(split)["IsFraud"].sum().to_dict())
    print("Fraud rate per split:", feature_df.groupby(split)["IsFraud"].mean().round(4).to_dict())

    print("\nMissingness among CNP rows (device/ip/location/card/merchant):")
    cnp = feature_df[feature_df["is_p2p"] == 0]
    for col in ("has_device_id", "has_ip_address", "has_location", "has_card_token"):
        print(f"  {col}: {1 - cnp[col].mean():.3f} missing")
    print(f"  is_merchant_missing: {cnp['is_merchant_missing'].mean():.3f}")

    print("\nFraud pattern breakdown (Scenario/Pattern -- labels.csv ground truth, "
          "analysis only, never a model feature):")
    print(feature_df[feature_df["IsFraud"] == 1]["Pattern"].value_counts())


if __name__ == "__main__":
    pd.set_option("display.max_rows", 50)
    main()
