"""Model Explainability Module using SHAP (TreeExplainer).

Provides global and local feature attribution for the Random Forest fraud model:
- Global: Feature importance bar plot and beeswarm summary plot.
- Local: Individual transaction explanation with directional risk contributions.
"""
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import joblib
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import shap

from ml.config import (
    DEFAULT_MODEL_PATH,
    EXPECTED_FEATURE_COLUMNS,
    ORDERED_CATEGORICAL_FEATURES,
    ORDERED_NUMERIC_FEATURES,
    POSITIVE_CLASS_INDEX,
)

REPORTS_FIGURES_DIR = Path(__file__).resolve().parents[1] / "ml" / "reports" / "figures"


class ModelExplainer:
    """Manages SHAP TreeExplainer lifecycle and feature attribution."""

    def __init__(self, pipeline: Any = None):
        """Initialize with an existing Scikit-learn Pipeline or load default."""
        if pipeline is None:
            if not DEFAULT_MODEL_PATH.exists():
                raise FileNotFoundError(f"Model artifact not found at {DEFAULT_MODEL_PATH}")
            pipeline = joblib.load(DEFAULT_MODEL_PATH)

        self.pipeline = pipeline
        self.preprocessor = pipeline.named_steps.get("preprocess")
        self.model = pipeline.named_steps.get("model")

        if self.preprocessor is None or self.model is None:
            raise ValueError("Pipeline must contain 'preprocess' and 'model' steps.")

        # Cache TreeExplainer lazily or eagerly
        self._explainer: shap.TreeExplainer | None = None
        self._preprocessed_feature_names: list[str] | None = None

    @property
    def explainer(self) -> shap.TreeExplainer:
        if self._explainer is None:
            self._explainer = shap.TreeExplainer(self.model)
        return self._explainer

    @property
    def preprocessed_feature_names(self) -> list[str]:
        if self._preprocessed_feature_names is None:
            raw_names = list(self.preprocessor.get_feature_names_out())
            # Clean transformer prefixes ('numeric__', 'categorical__')
            self._preprocessed_feature_names = [
                n.replace("numeric__", "").replace("categorical__", "") for n in raw_names
            ]
        return self._preprocessed_feature_names

    def get_base_value(self) -> float:
        """Return base expected fraud probability value (prior)."""
        ev = self.explainer.expected_value
        if isinstance(ev, (list, np.ndarray)):
            return float(ev[POSITIVE_CLASS_INDEX])
        return float(ev)

    def explain_instance(
        self,
        features: pd.DataFrame | dict,
        top_k: int = 5,
        aggregate_categoricals: bool = True,
    ) -> dict[str, Any]:
        """Explain a single transaction features input using SHAP TreeExplainer.

        Args:
            features: 1-row DataFrame or dictionary with the 30 expected model features.
            top_k: Number of highest-magnitude contributing features to return.
            aggregate_categoricals: Whether to sum one-hot dummy contributions back into parent category.

        Returns:
            Structured dictionary with 'top_reasons', 'base_value', and 'fraud_probability'.
        """
        if isinstance(features, dict):
            df = pd.DataFrame([features])
        elif isinstance(features, pd.DataFrame):
            df = features.copy()
        else:
            raise TypeError(f"features must be a DataFrame or dict, got {type(features)}")

        if len(df) != 1:
            raise ValueError(f"explain_instance expects exactly 1 row, got {len(df)}")

        # Validate and reorder columns
        missing = [c for c in EXPECTED_FEATURE_COLUMNS if c not in df.columns]
        if missing:
            raise ValueError(f"Missing required feature columns for explanation: {missing}")

        X = df[EXPECTED_FEATURE_COLUMNS]
        X_trans = self.preprocessor.transform(X)

        # Compute SHAP values
        raw_shap = self.explainer.shap_values(X_trans)

        # Handle SHAP output shapes
        # SHAP 0.54 TreeExplainer on binary classifier returns ndarray of shape (n_samples, n_features, 2)
        # or list of length 2 [class_0, class_1]
        if isinstance(raw_shap, list):
            class1_shap = raw_shap[POSITIVE_CLASS_INDEX][0]
        elif isinstance(raw_shap, np.ndarray):
            if raw_shap.ndim == 3:
                class1_shap = raw_shap[0, :, POSITIVE_CLASS_INDEX]
            elif raw_shap.ndim == 2:
                class1_shap = raw_shap[0, :]
            else:
                raise ValueError(f"Unexpected SHAP ndarray dimension: {raw_shap.shape}")
        else:
            raise TypeError(f"Unexpected SHAP values type: {type(raw_shap)}")

        base_val = self.get_base_value()
        prob = float(self.pipeline.predict_proba(X)[0, POSITIVE_CLASS_INDEX])

        feature_names = self.preprocessed_feature_names

        if aggregate_categoricals:
            # Map preprocessed one-hot dummies back to original feature names
            aggregated: dict[str, float] = {}
            for name, val in zip(feature_names, class1_shap):
                # Identify parent feature
                parent = name
                for cat in ORDERED_CATEGORICAL_FEATURES:
                    if name.startswith(f"{cat}_"):
                        parent = cat
                        break
                aggregated[parent] = aggregated.get(parent, 0.0) + float(val)

            # Sort by absolute contribution
            sorted_items = sorted(aggregated.items(), key=lambda kv: abs(kv[1]), reverse=True)
        else:
            sorted_items = sorted(
                zip(feature_names, [float(v) for v in class1_shap]),
                key=lambda kv: abs(kv[1]),
                reverse=True,
            )

        top_reasons = []
        for feat_name, contrib in sorted_items[:top_k]:
            direction = "INCREASES_RISK" if contrib > 0 else "DECREASES_RISK"
            top_reasons.append({
                "feature": feat_name,
                "contribution": round(contrib, 4),
                "direction": direction,
            })

        return {
            "top_reasons": top_reasons,
            "base_value": round(base_val, 4),
            "fraud_probability": round(prob, 4),
        }


def explain_transaction(
    transaction_features: pd.DataFrame | dict,
    model: Any = None,
    explainer: ModelExplainer | None = None,
    top_k: int = 5,
) -> dict[str, Any]:
    """Public interface to explain an individual transaction prediction.

    Args:
        transaction_features: 1-row DataFrame or dict containing the 30 model features.
        model: Optional Scikit-learn Pipeline (defaults to loaded production pipeline).
        explainer: Optional existing ModelExplainer instance (for performance/caching).
        top_k: Number of key reasons to include.

    Returns:
        Structured explanation dict:
        {
            "top_reasons": [
                {"feature": "...", "contribution": 0.18, "direction": "INCREASES_RISK"},
                ...
            ]
        }
    """
    if explainer is None:
        if model is not None:
            explainer = ModelExplainer(pipeline=model)
        else:
            explainer = ModelExplainer()

    return explainer.explain_instance(transaction_features, top_k=top_k)


def generate_global_explanations(
    features_df: pd.DataFrame,
    sample_size: int = 500,
    output_dir: Path | str | None = None,
    save_plots: bool = True,
    random_seed: int = 42,
) -> dict[str, Any]:
    """Compute global SHAP explanations and save summary visualizations.

    Args:
        features_df: DataFrame containing the 30 model features.
        sample_size: Number of transactions to sample for evaluation.
        output_dir: Directory to save figure files.
        save_plots: Whether to save PNG files.
        random_seed: Reproducibility seed.

    Returns:
        Dictionary of mean absolute SHAP feature importances.
    """
    out_dir = Path(output_dir) if output_dir else REPORTS_FIGURES_DIR
    out_dir.mkdir(parents=True, exist_ok=True)

    explainer_obj = ModelExplainer()
    preprocessor = explainer_obj.preprocessor
    explainer = explainer_obj.explainer

    # Sample rows
    n = min(len(features_df), sample_size)
    sampled_df = features_df[EXPECTED_FEATURE_COLUMNS].sample(n=n, random_state=random_seed)
    X_trans = preprocessor.transform(sampled_df)

    # Compute SHAP
    shap_vals = explainer.shap_values(X_trans)
    if isinstance(shap_vals, list):
        class1_shap = shap_vals[POSITIVE_CLASS_INDEX]
    elif isinstance(shap_vals, np.ndarray) and shap_vals.ndim == 3:
        class1_shap = shap_vals[:, :, POSITIVE_CLASS_INDEX]
    else:
        class1_shap = shap_vals

    clean_names = explainer_obj.preprocessed_feature_names

    # Mean absolute SHAP per feature
    mean_abs = np.mean(np.abs(class1_shap), axis=0)
    importance_ranking = sorted(
        zip(clean_names, [float(m) for m in mean_abs]), key=lambda x: x[1], reverse=True
    )

    if save_plots:
        # 1. Bar Chart: Mean Absolute SHAP Importance
        top_n = min(20, len(importance_ranking))
        top_features = importance_ranking[:top_n]
        names = [f[0] for f in reversed(top_features)]
        scores = [f[1] for f in reversed(top_features)]

        plt.figure(figsize=(10, 8))
        plt.barh(range(len(names)), scores, color="#1f77b4", edgecolor="black", alpha=0.85)
        plt.yticks(range(len(names)), names, fontsize=9)
        plt.xlabel("Mean |SHAP Value| (Average Impact on Fraud Score)", fontsize=11)
        plt.title(f"Global Feature Importance: Top {top_n} Factors (N={n})", fontsize=13, fontweight="bold")
        plt.grid(axis="x", linestyle="--", alpha=0.5)
        plt.tight_layout()
        bar_path = out_dir / "shap_feature_importance_bar.png"
        plt.savefig(bar_path, dpi=300)
        plt.close()

        # 2. Beeswarm / Summary Plot
        plt.figure(figsize=(11, 9))
        shap.summary_plot(
            class1_shap,
            features=X_trans,
            feature_names=clean_names,
            max_display=20,
            show=False,
        )
        plt.title(f"SHAP Summary (Beeswarm) Plot: Fraud Class (N={n})", fontsize=13, fontweight="bold", pad=15)
        plt.tight_layout()
        beeswarm_path = out_dir / "shap_summary_beeswarm.png"
        plt.savefig(beeswarm_path, dpi=300)
        plt.close()

    return {
        "sample_size": n,
        "feature_importances": dict(importance_ranking),
        "top_features": importance_ranking[:10],
    }


if __name__ == "__main__":
    from ml.features import MerchantRiskEncoder, build_features

    print("Generating global SHAP explanations on test dataset...")
    raw_df = pd.read_csv(
        Path(__file__).resolve().parents[1] / "ml" / "data" / "raw_features.csv",
        parse_dates=["TransactionTimestamp", "SenderAccountCreatedAt"],
    )
    features_df = build_features(raw_df)
    encoder = MerchantRiskEncoder.load(DEFAULT_MODEL_PATH.parent / "merchant_risk_encoder_disposable_33070.json")
    features_df["merchant_risk_rate"] = encoder.transform(features_df, is_train=False)

    summary = generate_global_explanations(features_df, sample_size=400)
    print("Global Top 5 features:")
    for feat, imp in summary["top_features"][:5]:
        print(f"  - {feat}: {imp:.4f}")

    # Test single explanation
    single_exp = explain_transaction(features_df.iloc[0:1])
    print("\nSingle transaction explanation test:")
    print(single_exp)
