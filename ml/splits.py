"""Time-aware train/validation/test split -- see docs/PHASE3_ML_DESIGN.md Section 5.

Never shuffled: fraud patterns like velocity_burst and fan_out depend on a
transaction's position in time, and shuffling would mix future transactions
into "earlier" training data.
"""
import pandas as pd

TRAIN_END = pd.Timestamp("2025-09-01")  # Jan-Aug train
VAL_END = pd.Timestamp("2025-11-01")    # Sep-Oct val, Nov-Dec test


def assign_split(timestamps: pd.Series) -> pd.Series:
    split = pd.Series("test", index=timestamps.index)
    split[timestamps < VAL_END] = "val"
    split[timestamps < TRAIN_END] = "train"
    return split
