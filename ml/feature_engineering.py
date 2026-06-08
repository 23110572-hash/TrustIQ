"""Feature extraction from raw banking-event signals.

Transforms a raw events DataFrame (from :mod:`synthetic_data`) into a numeric
feature matrix suitable for the Isolation Forest and downstream models, applying
privacy-preserving derived features only.
"""
from __future__ import annotations

import logging
from typing import List, Tuple

import numpy as np
import pandas as pd

logger = logging.getLogger("trustiq.features")

# The canonical ordered feature columns used by every model.
FEATURE_COLUMNS: List[str] = [
    "amount",
    "hour_of_day",
    "velocity_last_hour",
    "distance_from_home_km",
    "is_new_device",
    "is_vpn_or_tor",
    "dwell_mean",
    "flight_mean",
]


def engineer(df: pd.DataFrame) -> pd.DataFrame:
    """Add derived features and normalise raw event columns.

    Args:
        df: Raw events DataFrame.

    Returns:
        A copy of ``df`` with engineered feature columns added.
    """
    out = df.copy()

    # Boolean -> int.
    out["is_new_device"] = out["is_new_device"].astype(int)
    out["is_vpn_or_tor"] = out["is_vpn_or_tor"].astype(int)

    # Derived: night-time flag and log-scaled amount.
    out["is_night"] = ((out["hour_of_day"] >= 22) | (out["hour_of_day"] <= 6)).astype(int)
    out["log_amount"] = np.log1p(out["amount"])

    # Behavioural drift proxy: ratio of flight to dwell time.
    out["flight_dwell_ratio"] = out["flight_mean"] / out["dwell_mean"].replace(0, 1)

    logger.info("Engineered features for %d rows", len(out))
    return out


def to_matrix(df: pd.DataFrame) -> Tuple[np.ndarray, np.ndarray]:
    """Convert an engineered DataFrame into a model-ready matrix + labels.

    Args:
        df: An engineered events DataFrame (must contain FEATURE_COLUMNS).

    Returns:
        A tuple ``(X, y)`` where ``X`` is the feature matrix and ``y`` is a
        binary anomaly label (1 = any attack, 0 = normal).
    """
    feat = engineer(df) if "is_night" not in df.columns else df
    extra = ["is_night", "log_amount", "flight_dwell_ratio"]
    cols = FEATURE_COLUMNS + extra
    X = feat[cols].to_numpy(dtype=float)
    if "label" in feat.columns:
        y = (feat["label"] != "normal").astype(int).to_numpy()
    else:
        y = np.zeros(len(feat), dtype=int)
    return X, y
