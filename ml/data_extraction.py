"""Phase 3 data extraction: MySQL features + labels.csv target, merged in pandas.

The schema has no label column by design (see data_generation/README.md), so
the fraud label never comes from SQL. This script joins Transaction with
Account/AccountType/TransactionType/Merchant for features, then merges
labels.csv on TransactionID for the target, and caches the result to
ml/data/raw_features.csv so later steps don't need a live DB connection.

Excluded by design (see docs/ML_FEATURE_DICTIONARY.md Section 1):
Account.Balance, Account.AccountStatus (verified constant 'ACTIVE' for every
sender/receiver in this dataset per validate_data.py checks 81/82, so it
carries no signal here), Transaction.Status, FraudScore/FraudPrediction/
RiskStatus, Fraud_Alert/Investigation.

Usage: python ml/data_extraction.py [--force]
"""
import argparse
import sys
import warnings
from pathlib import Path

import pandas as pd

# pandas warns that a raw DBAPI2 connection (vs. SQLAlchemy) is untested;
# mysql-connector-python works fine here and this project's stack list
# allows either (docs/PROJECT_CONTEXT.md), so SQLAlchemy is skipped deliberately.
warnings.filterwarnings("ignore", message="pandas only supports SQLAlchemy connectable")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))  # so `from ml.db import get_connection` works when run directly

from ml.db import get_connection  # noqa: E402

OUTPUT_DIR = ROOT / "ml" / "data"
RAW_FEATURES_PATH = OUTPUT_DIR / "raw_features.csv"
LABELS_PATH = ROOT / "data_generation" / "output" / "labels.csv"

EXTRACTION_QUERY = """
SELECT
    t.TransactionID,
    t.TransactionTimestamp,
    t.Amount,
    t.SenderAccountNumber,
    t.ReceiverAccountNumber,
    t.ReceiverUPIID,
    tt.TypeName AS TransactionTypeName,
    t.MerchantID,
    m.Category AS MerchantCategory,
    t.DeviceID,
    t.IPAddress,
    t.Location,
    t.CardReferenceToken,
    sa.CustomerID AS SenderCustomerID,
    sat.TypeName AS SenderAccountType,
    sa.CreatedAt AS SenderAccountCreatedAt
FROM `Transaction` t
JOIN TransactionType tt ON tt.TransactionTypeID = t.TransactionTypeID
JOIN Account sa ON sa.AccountNumber = t.SenderAccountNumber
JOIN AccountType sat ON sat.AccountTypeID = sa.AccountTypeID
LEFT JOIN Merchant m ON m.MerchantID = t.MerchantID
ORDER BY t.TransactionTimestamp, t.TransactionID
"""


def extract(force: bool = False) -> pd.DataFrame:
    if RAW_FEATURES_PATH.exists() and not force:
        print(f"Using cached {RAW_FEATURES_PATH} (pass --force to re-extract).")
        return pd.read_csv(RAW_FEATURES_PATH, parse_dates=["TransactionTimestamp", "SenderAccountCreatedAt"])

    conn = get_connection()
    try:
        raw = pd.read_sql(EXTRACTION_QUERY, conn)
    finally:
        conn.close()

    labels = pd.read_csv(LABELS_PATH)
    merged = raw.merge(labels, on="TransactionID", how="inner", validate="one_to_one")
    if len(merged) != len(raw):
        raise RuntimeError(
            f"Label merge dropped rows: {len(raw)} transactions extracted, "
            f"{len(merged)} matched a label. labels.csv may be out of sync with the DB."
        )

    merged["TransactionTimestamp"] = pd.to_datetime(merged["TransactionTimestamp"])
    merged["SenderAccountCreatedAt"] = pd.to_datetime(merged["SenderAccountCreatedAt"])

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    merged.to_csv(RAW_FEATURES_PATH, index=False)
    print(f"Extracted {len(merged)} rows -> {RAW_FEATURES_PATH}")
    return merged


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true", help="Re-extract from MySQL even if a cached CSV exists.")
    args = parser.parse_args()
    df = extract(force=args.force)
    print(df["IsFraud"].value_counts(normalize=True))
