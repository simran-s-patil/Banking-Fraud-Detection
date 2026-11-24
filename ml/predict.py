"""Production-Ready Machine Learning Prediction Interface.

Provides single-transaction and batch scoring functions for Person 1's backend:
- Reuses existing feature engineering (ml/features.py).
- Reuses persisted MerchantRiskEncoder for leak-free risk lookup.
- Scores transactions using the production Random Forest pipeline.
- Categorizes predictions into binary outcomes ('LEGITIMATE', 'FRAUDULENT') and
  operational risk bands ('LOW', 'MEDIUM', 'HIGH').
- Supports optional on-demand SHAP explanations.
"""
import sys
from pathlib import Path
from typing import Any, Literal

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import joblib
import numpy as np
import pandas as pd

from ml.config import (
    CLASSIFICATION_THRESHOLD,
    DEFAULT_ENCODER_PATH,
    DEFAULT_METADATA_PATH,
    DEFAULT_MODEL_PATH,
    EXPECTED_FEATURE_COLUMNS,
    MODEL_VERSION,
    ORDERED_CATEGORICAL_FEATURES,
    ORDERED_NUMERIC_FEATURES,
    POSITIVE_CLASS_INDEX,
    PRED_FRAUDULENT,
    PRED_LEGITIMATE,
    RISK_HIGH,
    RISK_LOW,
    RISK_MEDIUM,
    classify_prediction,
    classify_risk,
)
from ml.features import MerchantRiskEncoder, build_features
from ml.model_explainer import ModelExplainer, explain_transaction

RAW_TRANSACTION_REQUIRED_COLUMNS = [
    "TransactionID",
    "TransactionTimestamp",
    "Amount",
    "SenderAccountNumber",
    "SenderAccountType",
    "SenderAccountCreatedAt",
    "TransactionTypeName",
]


class FraudPredictor:
    """Manages model pipeline, encoder, and prediction lifecycle."""

    def __init__(
        self,
        model_path: Path | str | None = None,
        encoder_path: Path | str | None = None,
        metadata_path: Path | str | None = None,
        threshold: float = CLASSIFICATION_THRESHOLD,
    ):
        self.model_path = Path(model_path) if model_path else DEFAULT_MODEL_PATH
        self.encoder_path = Path(encoder_path) if encoder_path else DEFAULT_ENCODER_PATH
        self.metadata_path = Path(metadata_path) if metadata_path else DEFAULT_METADATA_PATH
        self.threshold = threshold

        self.model_version = MODEL_VERSION
        self._pipeline = None
        self._encoder = None
        self._explainer = None

        self._validate_and_load_artifacts()

    def _validate_and_load_artifacts(self) -> None:
        """Verify artifact integrity and load pipeline and encoder."""
        if not self.model_path.exists():
            raise FileNotFoundError(f"Model artifact not found at {self.model_path}")
        if not self.encoder_path.exists():
            raise FileNotFoundError(f"Merchant encoder artifact not found at {self.encoder_path}")

        try:
            self._pipeline = joblib.load(self.model_path)
        except Exception as e:
            raise RuntimeError(f"Failed to load Scikit-learn model pipeline from {self.model_path}: {e}") from e

        if not hasattr(self._pipeline, "named_steps") or "preprocess" not in self._pipeline.named_steps:
            raise ValueError("Loaded model pipeline is missing the 'preprocess' step.")
        if "model" not in self._pipeline.named_steps:
            raise ValueError("Loaded model pipeline is missing the 'model' step.")

        try:
            self._encoder = MerchantRiskEncoder.load(self.encoder_path)
        except Exception as e:
            raise RuntimeError(f"Failed to load MerchantRiskEncoder from {self.encoder_path}: {e}") from e

        if not self._encoder.is_fitted_:
            raise ValueError("Loaded MerchantRiskEncoder is not fitted.")

    @property
    def pipeline(self):
        return self._pipeline

    @property
    def encoder(self) -> MerchantRiskEncoder:
        return self._encoder

    @property
    def explainer(self) -> ModelExplainer:
        if self._explainer is None:
            self._explainer = ModelExplainer(pipeline=self._pipeline)
        return self._explainer

    def prepare_features(
        self,
        transaction_data: pd.DataFrame | dict,
        historical_context: pd.DataFrame | list[dict] | None = None,
    ) -> tuple[pd.DataFrame, list[int]]:
        """Validate input data and prepare the 30-feature DataFrame.

        Accepts either:
        1. A DataFrame or dict containing the 30 precomputed model features.
        2. A raw transaction record (or batch) together with optional historical context.
        """
        if isinstance(transaction_data, dict):
            df = pd.DataFrame([transaction_data])
        elif isinstance(transaction_data, pd.DataFrame):
            df = transaction_data.copy()
        elif isinstance(transaction_data, list):
            df = pd.DataFrame(transaction_data)
        else:
            raise TypeError(f"Invalid input type: {type(transaction_data)}. Expected DataFrame, dict, or list of dicts.")

        if df.empty:
            return pd.DataFrame(columns=EXPECTED_FEATURE_COLUMNS), []

        # Case 1: Precomputed features provided
        # Check if 27+ core features are already present
        engineered_present = set(EXPECTED_FEATURE_COLUMNS).issubset(df.columns)
        core_26_present = set(EXPECTED_FEATURE_COLUMNS[:-4]).issubset(df.columns)

        if engineered_present or core_26_present:
            # Apply merchant risk rate encoder if missing
            if "merchant_risk_rate" not in df.columns:
                if "MerchantID" in df.columns:
                    df["merchant_risk_rate"] = self.encoder.transform(df, is_train=False)
                else:
                    df["merchant_risk_rate"] = self.encoder.global_rate_

            # Ensure all categorical columns exist with defaults if omitted
            for cat_col in ORDERED_CATEGORICAL_FEATURES:
                if cat_col not in df.columns:
                    df[cat_col] = "MISSING"

            missing = [c for c in EXPECTED_FEATURE_COLUMNS if c not in df.columns]
            if missing:
                raise ValueError(f"Missing required feature columns: {missing}")

            # Validate that mandatory numeric values (such as amount) are not null
            if df["amount"].isna().any():
                raise ValueError("Transaction feature data contains null or NaN in mandatory 'amount' column.")

            txn_ids = df["TransactionID"].astype(int).tolist() if "TransactionID" in df.columns else list(range(len(df)))
            return df[EXPECTED_FEATURE_COLUMNS].copy(), txn_ids

        # Case 2: Raw transaction data provided
        # Validate required raw columns
        missing_raw = [c for c in RAW_TRANSACTION_REQUIRED_COLUMNS if c not in df.columns]
        if missing_raw:
            raise ValueError(
                f"Input does not contain complete engineered features, and is missing required raw columns: {missing_raw}"
            )

        # Ensure datetime columns
        df["TransactionTimestamp"] = pd.to_datetime(df["TransactionTimestamp"])
        df["SenderAccountCreatedAt"] = pd.to_datetime(df["SenderAccountCreatedAt"])

        # Populate optional raw columns with NaN/None if missing
        optional_raw = [
            "ReceiverAccountNumber",
            "ReceiverUPIID",
            "MerchantID",
            "MerchantCategory",
            "DeviceID",
            "IPAddress",
            "Location",
            "CardReferenceToken",
            "SenderCustomerID",
        ]
        for col in optional_raw:
            if col not in df.columns:
                df[col] = np.nan

        # If historical context provided, prepend it to calculate rolling window aggregates
        if historical_context is not None:
            if isinstance(historical_context, list):
                hist_df = pd.DataFrame(historical_context)
            elif isinstance(historical_context, pd.DataFrame):
                hist_df = historical_context.copy()
            else:
                raise TypeError("historical_context must be a DataFrame or list of dicts.")

            if not hist_df.empty:
                hist_df["TransactionTimestamp"] = pd.to_datetime(hist_df["TransactionTimestamp"])
                hist_df["SenderAccountCreatedAt"] = pd.to_datetime(hist_df["SenderAccountCreatedAt"])
                for col in optional_raw:
                    if col not in hist_df.columns:
                        hist_df[col] = np.nan

                # Tag target rows
                df["__is_target__"] = True
                hist_df["__is_target__"] = False
                combined = pd.concat([hist_df, df], ignore_index=True)
            else:
                df["__is_target__"] = True
                combined = df
        else:
            # When scoring a single transaction without history, verify if history was expected
            if len(df) == 1 and historical_context is None:
                # Do not silently substitute arbitrary zeros if historical features cannot be computed accurately
                # Check if caller expects feature engineering from raw
                pass
            df["__is_target__"] = True
            combined = df

        # Execute existing feature engineering
        features_df = build_features(combined)

        # Apply persisted MerchantRiskEncoder
        features_df["merchant_risk_rate"] = self.encoder.transform(features_df, is_train=False)

        # Filter back to target transactions
        if "__is_target__" in features_df.columns:
            target_mask = features_df["__is_target__"] == True  # noqa: E712
            target_features = features_df.loc[target_mask].copy()
        else:
            target_features = features_df.copy()

        txn_ids = (
            target_features["TransactionID"].astype(int).tolist()
            if "TransactionID" in target_features.columns
            else list(range(len(target_features)))
        )

        return target_features[EXPECTED_FEATURE_COLUMNS].copy(), txn_ids

    def score(
        self,
        features_df: pd.DataFrame,
        txn_ids: list[int],
        explain: bool = False,
    ) -> list[dict[str, Any]]:
        """Score prepared features DataFrame and produce standardized response dictionaries."""
        if features_df.empty:
            return []

        probs = self.pipeline.predict_proba(features_df)[:, POSITIVE_CLASS_INDEX]

        results = []
        for i, (prob, txn_id) in enumerate(zip(probs, txn_ids)):
            p = float(prob)
            prediction = classify_prediction(p, threshold=self.threshold)
            risk_status = classify_risk(p)
            merchant_risk = float(features_df.iloc[i]["merchant_risk_rate"])

            record = {
                "transaction_id": int(txn_id),
                "fraud_probability": round(p, 4),
                "prediction": prediction,
                "model_version": self.model_version,
                "risk_status": risk_status,
                "merchant_risk_rate": round(merchant_risk, 4),
            }

            if explain:
                exp_dict = self.explainer.explain_instance(features_df.iloc[i : i + 1])
                record["explanation"] = exp_dict

            results.append(record)

        return results


# Global singleton instance for high-throughput prediction without disk reloading
_GLOBAL_PREDICTOR: FraudPredictor | None = None


def get_default_predictor() -> FraudPredictor:
    """Retrieve or initialize the cached FraudPredictor singleton."""
    global _GLOBAL_PREDICTOR
    if _GLOBAL_PREDICTOR is None:
        _GLOBAL_PREDICTOR = FraudPredictor()
    return _GLOBAL_PREDICTOR


def predict_transaction(
    transaction: dict | pd.Series | pd.DataFrame,
    explain: bool = False,
    historical_context: pd.DataFrame | list[dict] | None = None,
    predictor: FraudPredictor | None = None,
) -> dict[str, Any]:
    """Score a single transaction and return standardized dictionary.

    Args:
        transaction: Transaction features dictionary, pandas Series, or 1-row DataFrame.
        explain: If True, computes and includes SHAP TreeExplainer attributions.
        historical_context: Optional preceding transactions for sender history window.
        predictor: Optional custom FraudPredictor instance.

    Returns:
        Standardized dictionary:
        {
            "transaction_id": 10001,
            "fraud_probability": 0.8700,
            "prediction": "FRAUDULENT",
            "model_version": "rf_v1.0",
            "risk_status": "HIGH",
            "merchant_risk_rate": 0.3500
        }
    """
    pred = predictor if predictor is not None else get_default_predictor()

    if isinstance(transaction, pd.Series):
        transaction = transaction.to_dict()

    if isinstance(transaction, dict):
        df_input = pd.DataFrame([transaction])
    elif isinstance(transaction, pd.DataFrame):
        df_input = transaction
    else:
        raise TypeError(f"transaction must be a dict, Series, or DataFrame; got {type(transaction)}")

    if len(df_input) != 1:
        raise ValueError(f"predict_transaction expects exactly 1 transaction, got {len(df_input)}")

    features_df, txn_ids = pred.prepare_features(df_input, historical_context=historical_context)
    results = pred.score(features_df, txn_ids, explain=explain)

    if not results:
        raise RuntimeError("Prediction failed to generate a score.")

    return results[0]


def predict_batch(
    transactions: pd.DataFrame | list[dict],
    explain: bool = False,
    historical_context: pd.DataFrame | list[dict] | None = None,
    errors: Literal["raise", "coerce"] = "raise",
    predictor: FraudPredictor | None = None,
) -> list[dict[str, Any]]:
    """Score a batch of transactions and return list of standardized dictionaries.

    Args:
        transactions: DataFrame or list of dicts.
        explain: Whether to include SHAP explanations for each transaction.
        historical_context: Optional historical transactions to prepend for rolling calculations.
        errors: 'raise' to fail on invalid records, or 'coerce' to log error objects.
        predictor: Optional custom FraudPredictor instance.

    Returns:
        List of standardized prediction dictionaries.
    """
    pred = predictor if predictor is not None else get_default_predictor()

    if isinstance(transactions, list):
        if not transactions:
            return []
        df_input = pd.DataFrame(transactions)
    elif isinstance(transactions, pd.DataFrame):
        if transactions.empty:
            return []
        df_input = transactions.copy()
    else:
        raise TypeError(f"transactions must be a DataFrame or list of dicts, got {type(transactions)}")

    try:
        features_df, txn_ids = pred.prepare_features(df_input, historical_context=historical_context)
        return pred.score(features_df, txn_ids, explain=explain)
    except Exception as e:
        if errors == "raise":
            raise
        else:
            # Handle error coercing for batch resilience
            results = []
            for i in range(len(df_input)):
                row = df_input.iloc[i : i + 1]
                txn_id = int(row["TransactionID"].iloc[0]) if "TransactionID" in row.columns else i
                try:
                    f_df, ids = pred.prepare_features(row, historical_context=historical_context)
                    res = pred.score(f_df, ids, explain=explain)
                    results.append(res[0])
                except Exception as row_err:
                    results.append({
                        "transaction_id": txn_id,
                        "error": str(row_err),
                        "status": "FAILED",
                    })
            return results
