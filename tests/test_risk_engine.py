"""Unit tests for the core risk engine."""
from __future__ import annotations

import pytest

from identity_graph import IdentityGraph
from models import (
    ActionType,
    BankingEvent,
    BehavioralSignal,
    ContextSignal,
    DeviceSignal,
    ResponseAction,
    RiskBand,
)
from risk_engine import RiskEngine
from state import MockRedis


@pytest.fixture
def engine() -> RiskEngine:
    """Provide a risk engine backed by an isolated in-memory Redis."""
    return RiskEngine(MockRedis(), IdentityGraph())


def _normal_event() -> BankingEvent:
    """Build a low-risk normal login event."""
    return BankingEvent(
        user_id="user_normal",
        action=ActionType.LOGIN,
        behavioral=BehavioralSignal(
            dwell_times=[100, 98, 102], flight_times=[80, 82, 79],
            swipe_velocity=1.2, mouse_entropy=0.7, tap_pressure=0.5,
        ),
        device=DeviceSignal(
            device_id="dev_trusted", os="Android 14", browser="Chrome",
            screen_resolution="1080x2400", webgl_hash="abc123",
        ),
        context=ContextSignal(amount=500, ip_address="10.0.0.1", city="Mumbai",
                              hour_of_day=10, distance_from_home_km=2),
    )


def _attack_event() -> BankingEvent:
    """Build a high-risk transfer event (new device, night, far away, big amount)."""
    return BankingEvent(
        user_id="user_attack",
        action=ActionType.TRANSFER,
        behavioral=BehavioralSignal(
            dwell_times=[40, 200, 35], flight_times=[200, 30, 250],
            swipe_velocity=5.0, mouse_entropy=0.1, tap_pressure=0.95,
        ),
        device=DeviceSignal(
            device_id="dev_attacker", os="unknown", browser="unknown",
            screen_resolution="0x0", webgl_hash="x", is_vpn_or_tor=True,
        ),
        context=ContextSignal(amount=95000, ip_address="5.5.5.5", city="Foreignville",
                              hour_of_day=3, velocity_last_hour=8,
                              distance_from_home_km=900),
    )


def test_returns_valid_score_range(engine: RiskEngine):
    """The risk score must always be within 0-100."""
    result = engine.evaluate(_normal_event())
    assert 0 <= result.risk_score <= 100
    assert isinstance(result.risk_band, RiskBand)


def test_normal_event_is_low_risk(engine: RiskEngine):
    """A consistent normal login should pass with low friction."""
    # Warm up the baseline with a few repeats so behaviour is 'known'.
    for _ in range(3):
        engine.evaluate(_normal_event())
    result = engine.evaluate(_normal_event())
    assert result.risk_score < 60
    assert result.response_action in (
        ResponseAction.SILENT_PASS,
        ResponseAction.PUSH_NOTIFICATION,
    )


def test_attack_event_is_high_risk(engine: RiskEngine):
    """A clear account-takeover pattern should score high and step up auth."""
    result = engine.evaluate(_attack_event())
    assert result.risk_score >= 50
    assert result.response_action in (
        ResponseAction.STEP_UP_OTP,
        ResponseAction.BLOCK,
        ResponseAction.PUSH_NOTIFICATION,
    )


def test_factors_present_and_weighted(engine: RiskEngine):
    """Every response must expose four weighted contributing factors."""
    result = engine.evaluate(_normal_event())
    names = {f.name for f in result.factors}
    assert names == {"behavioral", "device", "transaction_anomaly", "identity_graph"}
    assert abs(sum(f.weight for f in result.factors) - 1.0) < 1e-6


def test_explanation_is_nonempty(engine: RiskEngine):
    """The explanation string should be human-readable and non-empty."""
    result = engine.evaluate(_attack_event())
    assert isinstance(result.explanation, str)
    assert len(result.explanation) > 10
