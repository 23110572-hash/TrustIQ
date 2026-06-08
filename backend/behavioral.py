"""Behavioral biometrics processor.

Converts raw behavioral signals (keystroke dynamics, swipe velocity, mouse
entropy, tap pressure) into a feature vector, compares it against a stored
per-user baseline using cosine similarity, and returns a behavioral anomaly
score in the range 0-1 (higher = more anomalous).
"""
from __future__ import annotations

import json
import logging
from typing import List, Tuple

import numpy as np

from models import BehavioralSignal
from privacy_layer import minimise

logger = logging.getLogger("trustiq.behavioral")


class BehavioralProcessor:
    """Process behavioral biometrics and score them against a user baseline."""

    BASELINE_KEY = "behavioral_baseline:{user_id}"

    def __init__(self, redis_client) -> None:
        """Initialise the processor.

        Args:
            redis_client: A Redis-compatible client used to read/write baselines.
        """
        self.redis = redis_client

    def _feature_vector(self, signal: BehavioralSignal) -> np.ndarray:
        """Build a fixed-length feature vector from a behavioral signal.

        Args:
            signal: The behavioral signal captured from the client.

        Returns:
            A 6-dimensional numpy feature vector.
        """
        dwell = np.asarray(signal.dwell_times, dtype=float)
        flight = np.asarray(signal.flight_times, dtype=float)
        derived = minimise(
            {
                "dwell": signal.dwell_times,
                "flight": signal.flight_times,
            }
        )
        return np.array(
            [
                derived.get("dwell_mean", dwell.mean() if dwell.size else 100.0),
                derived.get("dwell_std", dwell.std() if dwell.size else 10.0),
                derived.get("flight_mean", flight.mean() if flight.size else 80.0),
                signal.swipe_velocity,
                signal.mouse_entropy,
                signal.tap_pressure,
            ],
            dtype=float,
        )

    def _default_baseline(self) -> np.ndarray:
        """Return a sensible default baseline for first-time users.

        Returns:
            A 6-dimensional baseline feature vector.
        """
        return np.array([100.0, 12.0, 80.0, 1.2, 0.7, 0.5], dtype=float)

    def get_baseline(self, user_id: str) -> np.ndarray:
        """Fetch the stored behavioral baseline for a user.

        Args:
            user_id: The user whose baseline to retrieve.

        Returns:
            The baseline feature vector (default if none stored).
        """
        raw = self.redis.get(self.BASELINE_KEY.format(user_id=user_id))
        if raw:
            try:
                return np.asarray(json.loads(raw), dtype=float)
            except (ValueError, TypeError):
                logger.warning("Corrupt baseline for %s, using default", user_id)
        return self._default_baseline()

    def update_baseline(self, user_id: str, vector: np.ndarray, alpha: float = 0.2) -> None:
        """Update the user's baseline with an exponential moving average.

        Args:
            user_id: The user to update.
            vector: The latest feature vector.
            alpha: Smoothing factor (higher adapts faster).
        """
        baseline = self.get_baseline(user_id)
        updated = (1 - alpha) * baseline + alpha * vector
        self.redis.setex(
            self.BASELINE_KEY.format(user_id=user_id),
            86400 * 30,
            json.dumps(updated.tolist()),
        )

    @staticmethod
    def _cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
        """Compute cosine similarity between two vectors.

        Args:
            a: First vector.
            b: Second vector.

        Returns:
            Cosine similarity in the range -1..1 (1 = identical direction).
        """
        denom = (np.linalg.norm(a) * np.linalg.norm(b)) or 1e-9
        return float(np.dot(a, b) / denom)

    def score(self, user_id: str, signal: BehavioralSignal) -> Tuple[float, str]:
        """Return a behavioral anomaly score for a user event.

        Args:
            user_id: The user performing the action.
            signal: The behavioral signal to score.

        Returns:
            A tuple ``(anomaly_score, explanation)`` where the score is 0-1.
        """
        vector = self._feature_vector(signal)
        baseline = self.get_baseline(user_id)
        similarity = self._cosine_similarity(vector, baseline)

        # Map similarity (-1..1) to anomaly score (0..1).
        anomaly = float(np.clip((1.0 - similarity) / 2.0, 0.0, 1.0))

        # Magnitude deviation amplifies the score for large drifts.
        magnitude_drift = np.linalg.norm(vector - baseline) / (
            np.linalg.norm(baseline) or 1e-9
        )
        anomaly = float(np.clip(anomaly + 0.3 * min(magnitude_drift, 1.0), 0.0, 1.0))

        # Update the baseline only for low-anomaly (presumed-genuine) events.
        if anomaly < 0.5:
            self.update_baseline(user_id, vector)

        explanation = (
            f"behavioral similarity={similarity:.2f}, drift={magnitude_drift:.2f}"
        )
        logger.info("Behavioral score user=%s anomaly=%.2f", user_id, anomaly)
        return anomaly, explanation
