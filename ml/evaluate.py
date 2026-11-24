"""Shared metrics -- precision/recall/F1/confusion matrix/ROC-AUC/PR-AUC,
threshold tuning, and per-pattern recall breakdown.

Accuracy is deliberately not computed as a headline metric here (see
docs/PHASE3_ML_DESIGN.md Section 10): at a 3% base rate it rewards a
model that never predicts fraud, so it is actively misleading on its own.
"""
import numpy as np
import pandas as pd
from sklearn.metrics import (
    accuracy_score,
    average_precision_score,
    confusion_matrix,
    f1_score,
    precision_recall_curve,
    precision_score,
    recall_score,
    roc_auc_score,
)


def compute_metrics(y_true, y_prob, threshold: float) -> dict:
    y_pred = (y_prob >= threshold).astype(int)
    tn, fp, fn, tp = confusion_matrix(y_true, y_pred, labels=[0, 1]).ravel()
    return {
        "threshold": threshold,
        "precision": precision_score(y_true, y_pred, zero_division=0),
        "recall": recall_score(y_true, y_pred, zero_division=0),
        "f1": f1_score(y_true, y_pred, zero_division=0),
        "roc_auc": roc_auc_score(y_true, y_prob),
        "pr_auc": average_precision_score(y_true, y_prob),
        # Secondary, never the headline metric or a selection criterion -- at a
        # 3% base rate a model that never predicts fraud scores ~97% here.
        "accuracy_secondary_only": accuracy_score(y_true, y_pred),
        "confusion_matrix": {"tn": int(tn), "fp": int(fp), "fn": int(fn), "tp": int(tp)},
        "n_positive": int(np.sum(y_true)),
        "n_total": int(len(y_true)),
    }


def tune_threshold(y_true, y_prob, metric: str = "f1") -> dict:
    """Pick the probability threshold on this (validation) split that maximizes `metric`.

    Returns the chosen threshold plus a neighborhood of nearby thresholds and
    their precision/recall/F1, so the choice can be reported as a range, not
    a single knife-edge number -- see docs/PHASE3_ML_DESIGN.md Section 9 on
    why this matters when validation only has ~80 fraud rows.
    """
    precisions, recalls, thresholds = precision_recall_curve(y_true, y_prob)
    # precision_recall_curve returns one more precision/recall point than
    # thresholds (the last point is threshold=1.0 with no corresponding
    # entry); drop it so arrays align.
    precisions, recalls = precisions[:-1], recalls[:-1]
    with np.errstate(invalid="ignore", divide="ignore"):
        f1s = np.where((precisions + recalls) > 0, 2 * precisions * recalls / (precisions + recalls), 0.0)
    best_idx = int(np.argmax(f1s))
    best_threshold = float(thresholds[best_idx])

    neighborhood = []
    for delta in (-0.04, -0.02, 0.0, 0.02, 0.04):
        t = min(max(best_threshold + delta, 0.0), 1.0)
        neighborhood.append({"threshold": round(t, 4), **{k: v for k, v in compute_metrics(y_true, y_prob, t).items() if k in ("precision", "recall", "f1")}})

    return {"best_threshold": best_threshold, "best_f1": float(f1s[best_idx]), "neighborhood": neighborhood}


def per_pattern_recall(y_true, y_prob, pattern: pd.Series, threshold: float) -> dict:
    """Recall broken down by the generator's ground-truth Pattern column.

    Pattern/Scenario are never model inputs (docs/ML_FEATURE_DICTIONARY.md
    Section 6) -- this is the one place they're allowed, purely for
    post-hoc error analysis.
    """
    y_pred = (np.asarray(y_prob) >= threshold).astype(int)
    df = pd.DataFrame({"y_true": np.asarray(y_true), "y_pred": y_pred, "pattern": pattern.to_numpy()})
    fraud_rows = df[df["y_true"] == 1]
    out = {}
    for pattern_name, g in fraud_rows.groupby("pattern"):
        out[pattern_name] = {
            "n_fraud": int(len(g)),
            "recall": float((g["y_pred"] == 1).mean()),
        }
    return out
