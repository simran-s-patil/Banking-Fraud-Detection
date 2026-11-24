"""Phase 3 training: Logistic Regression baseline vs Random Forest, on the
seed-42 synthetic dataset, following docs/PHASE3_ML_DESIGN.md end to end.

Usage: python ml/train.py [--force-extract] [--dataset-source NAME]

`--dataset-source` tags every output filename and every record in the
sidecar/experiment-log JSON (e.g. "disposable_33070" vs "real_db_20261201"),
so a later run against a different database can never silently overwrite an
earlier run's models or metrics -- it refuses outright if the target file
already exists (see `_dump_model`). Default matches the only source this
script has ever been run against so far.

Never trains against the user's real database on its own -- data_extraction.py
refuses port 3306 without an explicit opt-in the user hasn't given, and this
script never sets that opt-in itself.
"""
import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ml.data_extraction import extract  # noqa: E402
from ml.evaluate import compute_metrics, per_pattern_recall, tune_threshold  # noqa: E402
from ml.features import (  # noqa: E402
    ABLATION_DROP_FEATURE,
    ALL_NUMERIC_FEATURES,
    CATEGORICAL_FEATURES,
    add_merchant_risk_rate,
    build_features,
)
from ml.splits import assign_split  # noqa: E402

SEED = 42
MODELS_DIR = ROOT / "ml" / "models"
EXPERIMENTS_DIR = ROOT / "ml" / "experiments"
MANIFEST_PATH = ROOT / "data_generation" / "output" / "manifest.json"

RF_CANDIDATES = [
    {"n_estimators": 300, "max_depth": None, "min_samples_leaf": 1},
    {"n_estimators": 300, "max_depth": 10, "min_samples_leaf": 5},
    {"n_estimators": 300, "max_depth": 6, "min_samples_leaf": 10},
]


def build_preprocessor(numeric_features: list[str]) -> ColumnTransformer:
    numeric_pipeline = Pipeline([
        ("impute", SimpleImputer(strategy="median")),  # safety net; engineered features already fill their own NaNs
        ("scale", StandardScaler()),
    ])
    categorical_pipeline = Pipeline([
        ("impute", SimpleImputer(strategy="constant", fill_value="MISSING")),
        ("encode", OneHotEncoder(handle_unknown="ignore")),
    ])
    return ColumnTransformer([
        ("numeric", numeric_pipeline, numeric_features),
        ("categorical", categorical_pipeline, CATEGORICAL_FEATURES),
    ])


def make_logistic_regression(numeric_features: list[str]) -> Pipeline:
    return Pipeline([
        ("preprocess", build_preprocessor(numeric_features)),
        ("model", LogisticRegression(class_weight="balanced", max_iter=2000, random_state=SEED)),
    ])


def select_random_forest(numeric_features, X_train, y_train, X_val, y_val) -> tuple[Pipeline, dict]:
    """Small manual grid over max_depth/min_samples_leaf, picked by validation PR-AUC.

    Not cross-validated: cross-validation would mix time-ordered folds and
    violate the chronological split (docs/PHASE3_ML_DESIGN.md Section 7).
    """
    best_pipeline, best_score, best_params = None, -1.0, None
    for params in RF_CANDIDATES:
        pipeline = Pipeline([
            ("preprocess", build_preprocessor(numeric_features)),
            ("model", RandomForestClassifier(class_weight="balanced_subsample", random_state=SEED, **params)),
        ])
        pipeline.fit(X_train, y_train)
        val_prob = pipeline.predict_proba(X_val)[:, 1]
        score = compute_metrics(y_val, val_prob, 0.5)["pr_auc"]
        if score > best_score:
            best_pipeline, best_score, best_params = pipeline, score, params
    return best_pipeline, {"params": best_params, "val_pr_auc_at_0.5": best_score}


def _dump_model(pipeline: Pipeline, name: str, label: str, dataset_source: str, sidecar: dict) -> Path:
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    model_path = MODELS_DIR / f"{name}_{label}_{dataset_source}.joblib"
    sidecar_path = model_path.with_suffix(".json")
    if model_path.exists() or sidecar_path.exists():
        raise FileExistsError(
            f"Refusing to overwrite existing Phase 3 artifact {model_path.name}. "
            "Use a different --dataset-source (e.g. 'real_db_20261201') for a new run, "
            "or delete the old files yourself first if you intend to replace them."
        )
    joblib.dump(pipeline, model_path)
    with open(sidecar_path, "w") as f:
        json.dump(sidecar, f, indent=2, default=str)
    return model_path


def run_experiment(
    numeric_features: list[str], feature_df: pd.DataFrame, split: pd.Series, label: str, dataset_source: str
) -> dict:
    scored = add_merchant_risk_rate(feature_df, split)
    feature_cols = numeric_features + CATEGORICAL_FEATURES

    X = {s: scored.loc[split == s, feature_cols] for s in ("train", "val", "test")}
    y = {s: scored.loc[split == s, "IsFraud"].to_numpy() for s in ("train", "val", "test")}

    results = {}
    logreg = make_logistic_regression(numeric_features)
    logreg.fit(X["train"], y["train"])

    rf, rf_selection = select_random_forest(numeric_features, X["train"], y["train"], X["val"], y["val"])

    for name, pipeline, extra in (("logistic_regression", logreg, {}), ("random_forest", rf, rf_selection)):
        val_prob = pipeline.predict_proba(X["val"])[:, 1]
        test_prob = pipeline.predict_proba(X["test"])[:, 1]
        threshold_info = tune_threshold(y["val"], val_prob)
        threshold = threshold_info["best_threshold"]

        val_metrics = compute_metrics(y["val"], val_prob, threshold)
        test_metrics = compute_metrics(y["test"], test_prob, threshold)
        pattern_recall = per_pattern_recall(
            y["test"], test_prob, scored.loc[split == "test", "Pattern"], threshold
        )

        results[name] = {
            "model_selection": extra,
            "threshold_tuning": threshold_info,
            "validation_metrics": val_metrics,
            "test_metrics": test_metrics,
            "test_recall_by_pattern": pattern_recall,
            "feature_count": len(feature_cols),
        }

        sidecar = {
            "model_name": name,
            "experiment_label": label,
            "dataset_source": dataset_source,
            "db_host": os.environ.get("ML_DB_HOST", "127.0.0.1 (default)"),
            "db_port": os.environ.get("ML_DB_PORT", "33070 (default)"),
            "feature_columns": feature_cols,
            "threshold": threshold,
            "validation_metrics": val_metrics,
            "test_metrics": test_metrics,
            "random_seed": SEED,
        }
        model_path = _dump_model(pipeline, name, label, dataset_source, sidecar)
        results[name]["model_path"] = str(model_path)

    return results


def main(force_extract: bool, dataset_source: str) -> None:
    raw = extract(force=force_extract)
    feature_df = build_features(raw)
    split = assign_split(feature_df["TransactionTimestamp"])

    print(f"Dataset source tag for this run: {dataset_source}")
    print("Split sizes:", split.value_counts().to_dict())
    print("Fraud rows per split:", feature_df.groupby(split)["IsFraud"].sum().to_dict())

    full_results = run_experiment(ALL_NUMERIC_FEATURES, feature_df, split, label="full", dataset_source=dataset_source)

    ablation_features = [f for f in ALL_NUMERIC_FEATURES if f != ABLATION_DROP_FEATURE]
    ablation_results = run_experiment(
        ablation_features, feature_df, split, label="ablation_no_high_risk_category", dataset_source=dataset_source
    )

    manifest_hash = None
    if MANIFEST_PATH.exists():
        manifest_hash = json.loads(MANIFEST_PATH.read_text())["sha256"]

    experiment_log = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "seed": SEED,
        "dataset_source": dataset_source,
        "db_host": os.environ.get("ML_DB_HOST", "127.0.0.1 (default)"),
        "db_port": os.environ.get("ML_DB_PORT", "33070 (default)"),
        "split_sizes": split.value_counts().to_dict(),
        "fraud_counts_by_split": feature_df.groupby(split)["IsFraud"].sum().to_dict(),
        "dataset_manifest_sha256": manifest_hash,
        "full_feature_results": full_results,
        "ablation_no_is_high_risk_category": ablation_results,
    }
    EXPERIMENTS_DIR.mkdir(parents=True, exist_ok=True)
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    log_path = EXPERIMENTS_DIR / f"run_{dataset_source}_{run_id}.json"
    with open(log_path, "w") as f:
        json.dump(experiment_log, f, indent=2, default=str)

    print(f"\nExperiment log written to {log_path}")
    for name in ("logistic_regression", "random_forest"):
        full = full_results[name]["test_metrics"]
        abl = ablation_results[name]["test_metrics"]
        print(f"\n{name} (test split, tuned threshold):")
        print(f"  full features:    precision={full['precision']:.3f} recall={full['recall']:.3f} "
              f"f1={full['f1']:.3f} roc_auc={full['roc_auc']:.3f} pr_auc={full['pr_auc']:.3f}")
        print(f"  w/o high-risk cat: precision={abl['precision']:.3f} recall={abl['recall']:.3f} "
              f"f1={abl['f1']:.3f} roc_auc={abl['roc_auc']:.3f} pr_auc={abl['pr_auc']:.3f}")
        merchant_anomaly_full = full_results[name]["test_recall_by_pattern"].get("merchant_anomaly")
        merchant_anomaly_abl = ablation_results[name]["test_recall_by_pattern"].get("merchant_anomaly")
        print(f"  merchant_anomaly recall: full={merchant_anomaly_full} ablation={merchant_anomaly_abl}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--force-extract", action="store_true")
    parser.add_argument(
        "--dataset-source",
        default="disposable_33070",
        help="Tag identifying where this run's data came from (e.g. 'real_db_20261201'). "
             "Must differ from any prior run's tag or the run is refused to avoid overwriting it.",
    )
    args = parser.parse_args()
    main(force_extract=args.force_extract, dataset_source=args.dataset_source)
