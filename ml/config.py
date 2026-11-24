"""Centralized Machine Learning Configuration & Model Versioning.

Defines operational risk bands, binary classification thresholds, model artifact
paths, feature schemas, and validation routines for Phase 2 inference.
"""
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

# Root directory of the repository
ROOT_DIR = Path(__file__).resolve().parents[1]

# Model versioning identifiers
MODEL_VERSION = "rf_v1.0"
MODEL_TYPE = "RandomForestClassifier"
FEATURE_SCHEMA_VERSION = "v1.0"

# Model artifact paths
DEFAULT_MODEL_PATH = ROOT_DIR / "ml" / "models" / "random_forest_full_disposable_33070.joblib"
DEFAULT_METADATA_PATH = ROOT_DIR / "ml" / "models" / "random_forest_full_disposable_33070.json"
DEFAULT_ENCODER_PATH = ROOT_DIR / "ml" / "models" / "merchant_risk_encoder_disposable_33070.json"

# Classification threshold (empirically derived on validation split for balanced F1)
CLASSIFICATION_THRESHOLD = 0.2100

# Operational Risk Status Definitions
RiskBand = Literal["LOW", "MEDIUM", "HIGH"]
PredictionLabel = Literal["LEGITIMATE", "FRAUDULENT"]

PRED_LEGITIMATE: PredictionLabel = "LEGITIMATE"
PRED_FRAUDULENT: PredictionLabel = "FRAUDULENT"

RISK_LOW: RiskBand = "LOW"
RISK_MEDIUM: RiskBand = "MEDIUM"
RISK_HIGH: RiskBand = "HIGH"

# Operational boundary thresholds
# LOW:    [0.00, 0.10)
# MEDIUM: [0.10, 0.21)
# HIGH:   [0.21, 1.00]
RISK_LOW_UPPER = 0.10
RISK_MEDIUM_UPPER = 0.21

# Positive fraud class index in model output
POSITIVE_CLASS_INDEX = 1

# Complete ordered list of 30 features expected by the model pipeline
ORDERED_NUMERIC_FEATURES = [
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
    "merchant_risk_rate",
]

ORDERED_CATEGORICAL_FEATURES = [
    "sender_account_type",
    "receiver_shape",
    "merchant_category",
]

EXPECTED_FEATURE_COLUMNS = ORDERED_NUMERIC_FEATURES + ORDERED_CATEGORICAL_FEATURES


@dataclass(frozen=True)
class ModelMetadata:
    """Immutable model metadata specification."""
    model_version: str = MODEL_VERSION
    model_type: str = MODEL_TYPE
    feature_schema_version: str = FEATURE_SCHEMA_VERSION
    model_artifact_path: str = str(DEFAULT_MODEL_PATH)
    merchant_encoder_artifact_path: str = str(DEFAULT_ENCODER_PATH)
    classification_threshold: float = CLASSIFICATION_THRESHOLD
    feature_columns: list[str] = field(default_factory=lambda: list(EXPECTED_FEATURE_COLUMNS))

    def to_dict(self) -> dict:
        return {
            "model_version": self.model_version,
            "model_type": self.model_type,
            "feature_schema_version": self.feature_schema_version,
            "model_artifact_path": self.model_artifact_path,
            "merchant_encoder_artifact_path": self.merchant_encoder_artifact_path,
            "classification_threshold": self.classification_threshold,
            "feature_columns": self.feature_columns,
        }


def classify_risk(fraud_probability: float) -> RiskBand:
    """Classify fraud probability into operational risk bands.

    Boundaries:
      - LOW:    0.00 <= fraud_probability < 0.10
      - MEDIUM: 0.10 <= fraud_probability < 0.21
      - HIGH:   0.21 <= fraud_probability <= 1.00

    Raises:
      ValueError: If fraud_probability is < 0.0 or > 1.0 (outside numerical tolerance).
    """
    if fraud_probability is None:
        raise ValueError("fraud_probability cannot be None.")

    try:
        prob = float(fraud_probability)
    except (TypeError, ValueError) as err:
        raise ValueError(f"fraud_probability must be a numeric float, got {type(fraud_probability)}: {err}")

    # Allow tiny numerical precision tolerance (e.g. -1e-7 or 1.0000001 from float representations)
    eps = 1e-6
    if prob < -eps or prob > 1.0 + eps:
        raise ValueError(f"fraud_probability must be within [0.0, 1.0], got {prob}")

    # Clamp slightly within bounds for boundary checks
    clamped = max(0.0, min(1.0, prob))

    if clamped < RISK_LOW_UPPER:
        return RISK_LOW
    elif clamped < RISK_MEDIUM_UPPER:
        return RISK_MEDIUM
    else:
        return RISK_HIGH


def classify_prediction(fraud_probability: float, threshold: float = CLASSIFICATION_THRESHOLD) -> PredictionLabel:
    """Classify fraud probability into binary prediction based on decision threshold."""
    if fraud_probability >= threshold:
        return PRED_FRAUDULENT
    return PRED_LEGITIMATE
