"""Category-aware feature engineering per docs/ML_FEATURE_DICTIONARY.md.

Every "prior history" feature (velocity, fan-out, new-receiver/new-merchant,
device/location-change) is computed using strictly earlier transactions only
by sorting the whole frame by TransactionTimestamp first and never looking
ahead. merchant_risk_rate is the one feature that uses the label, so it is
computed separately in `add_merchant_risk_rate`, after the train/val/test
split is known, with leave-one-out encoding on the training rows (see its
docstring) so it never leaks the target into itself.

Kept in sync by hand with data_generation/config.py (duplicated rather than
imported, to avoid a cross-package sys.path hack for five constants).
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd

NIGHT_HOURS = {0, 1, 2, 3, 4, 5}
FESTIVAL_DAYS = {
    pd.Timestamp("2025-01-14").date(),
    pd.Timestamp("2025-03-14").date(),
    pd.Timestamp("2025-08-27").date(),
    pd.Timestamp("2025-10-20").date(),
    pd.Timestamp("2025-12-25").date(),
}
HIGH_RISK_CATEGORIES = {"Gaming", "Digital Goods", "Jewellery", "Electronics"}

# Columns the model is allowed to see (docs/ML_FEATURE_DICTIONARY.md Section 1
# lists what's excluded and why -- Account.Balance, opening_balances.csv,
# Transaction.Status, FraudScore/FraudPrediction/RiskStatus, Fraud_Alert/
# Investigation, and labels.csv's own Scenario/Pattern columns never appear
# upstream of this module in the first place: data_extraction.py never
# selects them).
NUMERIC_FEATURES = [
    "amount",
    "amount_log",
    "amount_zscore_sender",
    "hour_of_day",
    "day_of_week",
    "is_night",
    "is_festival_day",
    "sender_account_age_days",
    "has_sender_history",
    "sender_txn_count_10m",
    "sender_txn_count_60m",
    "sender_txn_count_1440m",
    "sender_amount_sum_60m",
    "is_new_receiver",
    "sender_fanout_60m",
    "sender_fanout_1440m",
    "is_high_risk_category",
    "is_new_merchant_for_customer",
    "has_device_id",
    "has_ip_address",
    "has_location",
    "has_card_token",
    "is_merchant_missing",
    "device_changed_for_account",
    "location_changed_for_account",
    "has_device_history",
    # merchant_risk_rate is added later by add_merchant_risk_rate()
]
CATEGORICAL_FEATURES = [
    "sender_account_type",
    "receiver_shape",
    "merchant_category",
]
ABLATION_DROP_FEATURE = "is_high_risk_category"
# Full numeric list including merchant_risk_rate, which add_merchant_risk_rate()
# appends after the split is known -- see that function's docstring.
ALL_NUMERIC_FEATURES = NUMERIC_FEATURES + ["merchant_risk_rate"]


def _sender_prior_features(g: pd.DataFrame) -> dict:
    """One sender's trailing-window stats, current row excluded from each.

    pandas time-rolling windows are inclusive of the current row, so each
    inclusive aggregate is computed once and then corrected (count - 1,
    sum - current amount) rather than re-running the aggregate with the row
    removed, which would be equivalent but slower.
    """
    indexed = g.set_index("TransactionTimestamp")["amount"]
    count_10 = indexed.rolling("10min").count() - 1
    count_60 = indexed.rolling("60min").count() - 1
    count_1440 = indexed.rolling("1440min").count() - 1
    sum_60 = indexed.rolling("60min").sum() - indexed
    prior_mean = indexed.shift().expanding().mean()
    prior_std = indexed.shift().expanding().std()
    return {
        "sender_txn_count_10m": count_10.to_numpy(),
        "sender_txn_count_60m": count_60.to_numpy(),
        "sender_txn_count_1440m": count_1440.to_numpy(),
        "sender_amount_sum_60m": sum_60.to_numpy(),
        "_prior_mean": prior_mean.to_numpy(),
        "_prior_std": prior_std.to_numpy(),
    }


def _fanout_counts(g: pd.DataFrame) -> dict:
    """Distinct receivers in the trailing 60min/1440min window, current row excluded.

    Single forward pass per sender: `seen` only ever holds receivers from
    rows processed so far, so the current row is excluded by construction
    (it's appended only after its own counts are read).
    """
    fanout_60, fanout_1440 = [], []
    seen: list[tuple] = []
    for ts, receiver in zip(g["TransactionTimestamp"], g["receiver_key"]):
        cutoff_60 = ts - pd.Timedelta("60min")
        cutoff_1440 = ts - pd.Timedelta("1440min")
        fanout_60.append(len({r for t, r in seen if t > cutoff_60}))
        fanout_1440.append(len({r for t, r in seen if t > cutoff_1440}))
        seen.append((ts, receiver))
    return {"sender_fanout_60m": fanout_60, "sender_fanout_1440m": fanout_1440}


def _device_location_change(g: pd.DataFrame) -> dict:
    """Device/location differing from this account's last known one (CNP rows only)."""
    device_changed, location_changed, has_history = [], [], []
    last_device, last_location, seen_any = None, None, False
    for device, location in zip(g["DeviceID"], g["Location"]):
        has_history.append(1 if seen_any else 0)
        device_changed.append(1 if (seen_any and pd.notna(device) and device != last_device) else 0)
        location_changed.append(1 if (seen_any and pd.notna(location) and location != last_location) else 0)
        if pd.notna(device):
            last_device, seen_any = device, True
        if pd.notna(location):
            last_location, seen_any = location, True
    return {
        "device_changed_for_account": device_changed,
        "location_changed_for_account": location_changed,
        "has_device_history": has_history,
    }


def build_features(raw: pd.DataFrame) -> pd.DataFrame:
    df = raw.sort_values(["TransactionTimestamp", "TransactionID"]).reset_index(drop=True).copy()
    df["is_p2p"] = (df["TransactionTypeName"] == "P2P_UPI").astype(int)

    # ---- Common ----
    df["amount"] = df["Amount"].astype(float)
    df["amount_log"] = np.log1p(df["amount"])
    df["hour_of_day"] = df["TransactionTimestamp"].dt.hour
    df["day_of_week"] = df["TransactionTimestamp"].dt.dayofweek
    df["is_night"] = df["hour_of_day"].isin(NIGHT_HOURS).astype(int)
    df["is_festival_day"] = df["TransactionTimestamp"].dt.date.map(lambda d: d in FESTIVAL_DAYS).astype(int)
    df["sender_account_type"] = df["SenderAccountType"]
    df["sender_account_age_days"] = (df["TransactionTimestamp"] - df["SenderAccountCreatedAt"]).dt.days

    df["receiver_key"] = np.where(
        df["ReceiverAccountNumber"].notna(),
        "acct:" + df["ReceiverAccountNumber"].astype("Int64").astype(str),
        np.where(df["ReceiverUPIID"].notna(), "upi:" + df["ReceiverUPIID"].astype(str), "none"),
    )
    df["receiver_shape"] = np.where(
        df["is_p2p"] == 0,
        "NOT_APPLICABLE",
        np.where(
            df["ReceiverAccountNumber"].notna() & df["ReceiverUPIID"].notna(),
            "account_and_upi",
            np.where(df["ReceiverAccountNumber"].notna(), "account_only", "external_upi_only"),
        ),
    )

    sender_groups = df.groupby("SenderAccountNumber", group_keys=False, sort=False)
    df["has_sender_history"] = (sender_groups.cumcount() > 0).astype(int)

    sender_cols = ["sender_txn_count_10m", "sender_txn_count_60m", "sender_txn_count_1440m",
                   "sender_amount_sum_60m", "_prior_mean", "_prior_std"]
    for col in sender_cols:
        df[col] = np.nan
    for _, g in sender_groups:
        result = _sender_prior_features(g)
        for col, values in result.items():
            df.loc[g.index, col] = values

    safe_std = df["_prior_std"].replace(0, np.nan)
    df["amount_zscore_sender"] = ((df["amount"] - df["_prior_mean"]) / safe_std).fillna(0.0)
    df.drop(columns=["_prior_mean", "_prior_std"], inplace=True)

    # ---- P2P-specific (0/"not applicable" for CNP rows) ----
    df["is_new_receiver"] = 0
    df["sender_fanout_60m"] = 0.0
    df["sender_fanout_1440m"] = 0.0
    p2p_mask = df["is_p2p"] == 1
    p2p = df[p2p_mask]
    first_occurrence = ~p2p.duplicated(subset=["SenderAccountNumber", "receiver_key"], keep="first")
    df.loc[p2p.index, "is_new_receiver"] = first_occurrence.astype(int).to_numpy()
    for _, g in p2p.groupby("SenderAccountNumber", group_keys=False, sort=False):
        result = _fanout_counts(g)
        for col, values in result.items():
            df.loc[g.index, col] = values

    # ---- CNP-specific (0/"not applicable" for P2P rows; confirmed empirically
    # that the generator only populates Device/IP/Location/CardReferenceToken/
    # Merchant for CNP rows -- see handoff.md 2026-11-23 follow-up) ----
    df["merchant_category"] = df["MerchantCategory"].fillna("NOT_APPLICABLE")
    df["is_high_risk_category"] = df["MerchantCategory"].isin(HIGH_RISK_CATEGORIES).astype(int)
    df["has_device_id"] = df["DeviceID"].notna().astype(int)
    df["has_ip_address"] = df["IPAddress"].notna().astype(int)
    df["has_location"] = df["Location"].notna().astype(int)
    df["has_card_token"] = df["CardReferenceToken"].notna().astype(int)
    df["is_merchant_missing"] = df["MerchantID"].isna().astype(int)

    df["is_new_merchant_for_customer"] = 0
    df["device_changed_for_account"] = 0
    df["location_changed_for_account"] = 0
    df["has_device_history"] = 0
    cnp_mask = df["is_p2p"] == 0
    cnp = df[cnp_mask]
    valid_merchant = cnp[cnp["MerchantID"].notna()]
    first_occ_merchant = ~valid_merchant.duplicated(subset=["SenderCustomerID", "MerchantID"], keep="first")
    df.loc[valid_merchant.index, "is_new_merchant_for_customer"] = first_occ_merchant.astype(int).to_numpy()
    for _, g in cnp.groupby("SenderAccountNumber", group_keys=False, sort=False):
        result = _device_location_change(g)
        for col, values in result.items():
            df.loc[g.index, col] = values

    keep = (
        ["TransactionID", "TransactionTimestamp", "TransactionTypeName", "is_p2p",
         "IsFraud", "Scenario", "Pattern", "MerchantID"]
        + NUMERIC_FEATURES
        + CATEGORICAL_FEATURES
    )
    return df[keep].copy()


class MerchantRiskEncoder:
    """Serializable, leak-free target encoder for merchant fraud risk.

    Encodes MerchantID as the historical fraud rate computed exclusively on
    the training split. During training, leave-one-out (LOO) encoding is used so
    that a transaction's own label never informs its own feature.
    During validation, testing, and live inference, the precomputed training-only
    merchant mean is mapped directly without labels. Unseen merchants, missing
    merchants, or non-merchant (P2P) rows fall back to the global training rate.
    """

    def __init__(self, fallback_rate: float | None = None):
        self.fallback_rate: float | None = fallback_rate
        self.global_rate_: float = fallback_rate if fallback_rate is not None else 0.0
        self.merchant_rates_: dict[str, float] = {}
        self.merchant_counts_: dict[str, int] = {}
        self.merchant_sums_: dict[str, float] = {}
        self.is_fitted_: bool = False

    def fit(self, train_df: pd.DataFrame, merchant_col: str = "MerchantID", target_col: str = "IsFraud") -> "MerchantRiskEncoder":
        if target_col not in train_df.columns:
            raise ValueError(f"Target column '{target_col}' missing from training dataframe.")
        valid = train_df[train_df[merchant_col].notna()]
        self.global_rate_ = float(train_df[target_col].mean())
        if self.fallback_rate is None:
            self.fallback_rate = self.global_rate_

        grouped = valid.groupby(merchant_col)[target_col].agg(["sum", "count"])
        self.merchant_sums_ = {str(int(k)): float(v) for k, v in grouped["sum"].to_dict().items()}
        self.merchant_counts_ = {str(int(k)): int(v) for k, v in grouped["count"].to_dict().items()}
        self.merchant_rates_ = {
            k: self.merchant_sums_[k] / self.merchant_counts_[k]
            for k in self.merchant_sums_
        }
        self.is_fitted_ = True
        return self

    def transform(
        self,
        df: pd.DataFrame,
        is_train: bool = False,
        merchant_col: str = "MerchantID",
        target_col: str = "IsFraud",
    ) -> pd.Series:
        if not self.is_fitted_:
            raise RuntimeError("MerchantRiskEncoder must be fitted or loaded before transform.")

        fallback = self.fallback_rate if self.fallback_rate is not None else self.global_rate_
        rate = pd.Series(fallback, index=df.index, dtype=float)

        valid_mask = df[merchant_col].notna()
        if not valid_mask.any():
            return rate

        valid_merchants = df.loc[valid_mask, merchant_col]
        # Format key as str(int(val)) matching the fit keys
        m_keys = valid_merchants.astype(int).astype(str)

        if is_train:
            if target_col not in df.columns:
                raise ValueError(f"Training transform requires '{target_col}' for leave-one-out calculation.")

            m_counts = m_keys.map(self.merchant_counts_).fillna(0).to_numpy()
            m_sums = m_keys.map(self.merchant_sums_).fillna(0.0).to_numpy()
            y = df.loc[valid_mask, target_col].to_numpy()

            denom = m_counts - 1
            with np.errstate(divide="ignore", invalid="ignore"):
                loo = np.where(denom > 0, (m_sums - y) / denom, fallback)
            rate.loc[valid_mask] = loo
        else:
            mapped = m_keys.map(self.merchant_rates_).fillna(fallback).to_numpy()
            rate.loc[valid_mask] = mapped

        return rate

    def to_dict(self) -> dict:
        return {
            "global_rate": self.global_rate_,
            "fallback_rate": self.fallback_rate,
            "merchant_rates": self.merchant_rates_,
            "merchant_counts": self.merchant_counts_,
            "merchant_sums": self.merchant_sums_,
            "is_fitted": self.is_fitted_,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "MerchantRiskEncoder":
        enc = cls(fallback_rate=data.get("fallback_rate", data.get("global_rate", 0.0)))
        enc.global_rate_ = data.get("global_rate", 0.0)
        enc.merchant_rates_ = data.get("merchant_rates", {})
        enc.merchant_counts_ = data.get("merchant_counts", {})
        enc.merchant_sums_ = data.get("merchant_sums", {})
        enc.is_fitted_ = data.get("is_fitted", True)
        return enc

    def save(self, filepath: str | Path) -> None:
        path = Path(filepath)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            json.dump(self.to_dict(), f, indent=2)

    @classmethod
    def load(cls, filepath: str | Path) -> "MerchantRiskEncoder":
        path = Path(filepath)
        with open(path, "r") as f:
            data = json.load(f)
        return cls.from_dict(data)


def add_merchant_risk_rate(df: pd.DataFrame, split: pd.Series) -> pd.DataFrame:
    """Merchant fraud-rate feature, fit on the training split only.

    Training rows get a leave-one-out rate -- (merchant's train fraud count
    minus this row's own label) / (merchant's train count minus one) -- so a
    row's own label never informs its own feature value, which is the usual
    target-encoding leakage trap even when the encoding itself is "trained on
    train only". Validation/test rows get the plain train-only mean, looked
    up (never recomputed from val/test labels). Rows with no merchant (every
    P2P row, plus the ~2% CNP edge case) or a merchant unseen in training
    fall back to the global training fraud rate.
    """
    df = df.copy()
    train_mask = (split == "train").to_numpy()
    train = df.loc[train_mask]
    global_rate = train["IsFraud"].mean()

    merchant_sum = train.groupby("MerchantID")["IsFraud"].sum()
    merchant_count = train.groupby("MerchantID")["IsFraud"].count()
    plain_rate = (merchant_sum / merchant_count).to_dict()

    rate = pd.Series(global_rate, index=df.index, dtype=float)

    train_merchant_count = train["MerchantID"].map(merchant_count)
    train_loo = (train["MerchantID"].map(merchant_sum) - train["IsFraud"]) / (train_merchant_count - 1)
    train_loo = train_loo.where(train_merchant_count > 1, global_rate)
    train_loo = train_loo.where(train["MerchantID"].notna(), global_rate)
    rate.loc[train_mask] = train_loo.to_numpy()

    other_mask = ~train_mask
    mapped = df.loc[other_mask, "MerchantID"].map(plain_rate)
    rate.loc[other_mask] = mapped.fillna(global_rate).to_numpy()

    df["merchant_risk_rate"] = rate
    return df
