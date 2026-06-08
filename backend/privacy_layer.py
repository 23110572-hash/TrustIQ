"""Privacy layer: PII anonymisation and differential privacy.

This module enforces three principles:

1. **Anonymisation** - user IDs and account numbers are hashed/masked before
   they reach any feature-engineering or logging path.
2. **Differential privacy** - Laplace noise is added to behavioral feature
   vectors prior to model training so individual records cannot be recovered.
3. **Data minimisation** - helpers return only derived features, never the raw
   behavioral streams.
"""
from __future__ import annotations

import hashlib
import logging
from typing import List

import numpy as np

from config import get_settings

logger = logging.getLogger("trustiq.privacy")

try:  # diffprivlib is optional; fall back to a manual Laplace mechanism.
    from diffprivlib.mechanisms import Laplace as _DPLaplace

    _DIFFPRIV_AVAILABLE = True
except Exception:  # pragma: no cover - exercised only when lib missing
    _DIFFPRIV_AVAILABLE = False
    logger.warning("diffprivlib unavailable - using numpy Laplace fallback.")


def hash_user_id(user_id: str) -> str:
    """Return a deterministic salted SHA-256 hash of a user identifier.

    Args:
        user_id: The raw user identifier.

    Returns:
        A 16-character hex digest suitable for joins without exposing the PII.
    """
    settings = get_settings()
    digest = hashlib.sha256(f"{settings.pii_salt}:{user_id}".encode()).hexdigest()
    return digest[:16]


def mask_account_number(account: str) -> str:
    """Mask an account number, keeping only the last four digits.

    Args:
        account: The raw account number.

    Returns:
        A masked representation, e.g. ``****-****-1234``.
    """
    if not account:
        return "****"
    last4 = account[-4:]
    return f"****-****-{last4}"


def mask_user_id(user_id: str) -> str:
    """Return a display-safe masked user id for dashboards and alerts.

    Args:
        user_id: The raw user identifier.

    Returns:
        A masked string showing only a short hash prefix.
    """
    return f"usr_{hash_user_id(user_id)[:8]}"


def add_differential_privacy_noise(
    features: List[float], epsilon: float | None = None, sensitivity: float | None = None
) -> List[float]:
    """Add calibrated Laplace noise to a feature vector for DP guarantees.

    Args:
        features: The raw numeric feature vector.
        epsilon: Privacy budget; lower means more privacy / more noise.
        sensitivity: Maximum change one record can have on the output.

    Returns:
        A new feature vector with differential-privacy noise applied.
    """
    settings = get_settings()
    eps = epsilon if epsilon is not None else settings.dp_epsilon
    sens = sensitivity if sensitivity is not None else settings.dp_sensitivity

    noised: List[float] = []
    if _DIFFPRIV_AVAILABLE:
        mech = _DPLaplace(epsilon=eps, sensitivity=sens)
        for value in features:
            noised.append(float(mech.randomise(float(value))))
    else:
        scale = sens / max(eps, 1e-9)
        noise = np.random.laplace(0.0, scale, size=len(features))
        noised = [float(v + n) for v, n in zip(features, noise)]
    return noised


def minimise(raw_features: dict) -> dict:
    """Apply data minimisation, returning only derived/aggregated features.

    Raw behavioral streams (individual keystroke arrays) are collapsed into
    summary statistics so the original sequence cannot be reconstructed.

    Args:
        raw_features: A dictionary that may contain raw streams.

    Returns:
        A dictionary containing only derived aggregate features.
    """
    derived: dict = {}
    for key, value in raw_features.items():
        if isinstance(value, (list, tuple)) and value:
            arr = np.asarray(value, dtype=float)
            derived[f"{key}_mean"] = float(arr.mean())
            derived[f"{key}_std"] = float(arr.std())
        elif isinstance(value, (int, float)):
            derived[key] = float(value)
    return derived
