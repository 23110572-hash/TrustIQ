"""Zero-trust account-recovery module.

Replaces fragile SMS-OTP recovery with a multi-signal identity proof chain:

* trusted-device history match
* behavioral baseline similarity
* recovery-channel risk (SMS < Email < Biometric < In-person)
* geographic plausibility
* time since last successful login

Returns a recovery risk score and the verification tier required.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import List

from behavioral import BehavioralProcessor
from device_fingerprint import DeviceFingerprinter
from models import RecoveryAttempt, RecoveryResult, RecoveryTier

logger = logging.getLogger("trustiq.recovery")

# Lower channel-risk values are *more* secure.
_CHANNEL_RISK = {"sms": 0.9, "email": 0.6, "biometric": 0.2, "in_person": 0.05}


class AccountRecoveryGuard:
    """Evaluate account-recovery attempts under a zero-trust model."""

    def __init__(self, redis_client) -> None:
        """Initialise the guard with shared behavioral/device scorers.

        Args:
            redis_client: Redis-compatible client for baselines / devices.
        """
        self.behavioral = BehavioralProcessor(redis_client)
        self.device = DeviceFingerprinter(redis_client)

    def evaluate(self, attempt: RecoveryAttempt) -> RecoveryResult:
        """Evaluate a recovery attempt and return a scored verification tier.

        Args:
            attempt: The account-recovery attempt to evaluate.

        Returns:
            A populated :class:`RecoveryResult`.
        """
        flags: List[str] = []

        # 1. Device trust (0-1, higher = trusted).
        device_trust, device_flags, _ = self.device.score(attempt.user_id, attempt.device)
        flags.extend(device_flags)
        device_risk = (1.0 - device_trust) * 100.0

        # 2. Behavioral similarity (0-1 anomaly).
        behav_anom, _ = self.behavioral.score(attempt.user_id, attempt.behavioral)
        behavioral_risk = behav_anom * 100.0
        if behav_anom > 0.6:
            flags.append("behavioral_mismatch")

        # 3. Recovery channel risk.
        channel_risk = _CHANNEL_RISK.get(attempt.recovery_channel.lower(), 0.9) * 100.0

        # 4. Geographic plausibility.
        geo_risk = min(attempt.context.distance_from_home_km / 10.0, 100.0)
        if attempt.context.distance_from_home_km > 500:
            flags.append("implausible_geography")

        # 5. Liveness.
        liveness_risk = 0.0 if attempt.liveness_passed else 80.0
        if not attempt.liveness_passed:
            flags.append("liveness_failed")

        # 6. Recency: long dormancy is riskier.
        recency_risk = min(attempt.hours_since_last_login / 24.0, 30.0)

        recovery_risk = (
            device_risk * 0.25
            + behavioral_risk * 0.20
            + channel_risk * 0.20
            + geo_risk * 0.15
            + liveness_risk * 0.15
            + recency_risk * 0.05
        )
        recovery_risk = float(max(0.0, min(100.0, recovery_risk)))

        tier = self._tier(recovery_risk, attempt)

        explanation = (
            f"Recovery risk {recovery_risk:.0f}: device={device_risk:.0f}, "
            f"behavioral={behavioral_risk:.0f}, channel={channel_risk:.0f}, "
            f"geo={geo_risk:.0f}, liveness={'FAIL' if not attempt.liveness_passed else 'pass'} "
            f"-> {tier.value}."
        )
        logger.info("Recovery user=%s risk=%.0f tier=%s",
                    attempt.user_id, recovery_risk, tier.value)

        return RecoveryResult(
            user_id=attempt.user_id,
            recovery_risk_score=round(recovery_risk, 2),
            recommended_tier=tier,
            risk_flags=flags,
            explanation=explanation,
            timestamp=datetime.now(timezone.utc),
        )

    @staticmethod
    def _tier(risk: float, attempt: RecoveryAttempt) -> RecoveryTier:
        """Map a recovery risk score to a verification tier.

        Args:
            risk: The 0-100 recovery risk score.
            attempt: The original attempt (used for hard blocks).

        Returns:
            The recommended :class:`RecoveryTier`.
        """
        # Failed liveness is an immediate block regardless of score.
        if not attempt.liveness_passed and risk >= 60:
            return RecoveryTier.BLOCKED
        if risk <= 25:
            return RecoveryTier.AUTO_APPROVE
        if risk <= 50:
            return RecoveryTier.EMAIL_VERIFY
        if risk <= 75:
            return RecoveryTier.BIOMETRIC_VERIFY
        if risk <= 90:
            return RecoveryTier.IN_PERSON
        return RecoveryTier.BLOCKED
