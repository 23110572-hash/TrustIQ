"""Unit tests for the anomaly detector (Isolation Forest + sequence model)."""
from __future__ import annotations

from anomaly_detector import AnomalyDetector
from models import ActionType, BankingEvent, ContextSignal


def _event(amount: float, hour: int, velocity: int, distance: float) -> BankingEvent:
    """Build a banking event with the given transaction context."""
    return BankingEvent(
        user_id="u",
        action=ActionType.TRANSFER,
        context=ContextSignal(
            amount=amount,
            hour_of_day=hour,
            velocity_last_hour=velocity,
            distance_from_home_km=distance,
        ),
    )


def test_detect_returns_probability_and_features():
    """detect() returns a 0-1 probability plus ranked features."""
    det = AnomalyDetector()
    prob, top = det.detect(_event(5000, 13, 1, 3))
    assert 0.0 <= prob <= 1.0
    assert len(top) == 3
    assert "feature" in top[0]


def test_extreme_transaction_more_anomalous_than_normal():
    """An extreme transfer should score at least as anomalous as a normal one."""
    det = AnomalyDetector()
    normal, _ = det.detect(_event(4000, 12, 1, 2))
    extreme, _ = det.detect(_event(500000, 3, 20, 2000))
    assert extreme >= normal


def test_sequence_anomaly_short_sequence_is_zero():
    """A single-action sequence cannot be anomalous."""
    det = AnomalyDetector()
    assert det.sequence_anomaly([0]) == 0.0


def test_sequence_anomaly_range():
    """Sequence anomaly scores stay within 0-1."""
    det = AnomalyDetector()
    score = det.sequence_anomaly([0, 1, 2, 3, 4, 0, 1])
    assert 0.0 <= score <= 1.0
