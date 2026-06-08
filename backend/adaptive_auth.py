"""Adaptive step-up authentication logic.

Maps a numeric risk score to a friction-optimised response:

* 0-30   -> silent pass (no friction)
* 31-60  -> push notification to trusted device
* 61-80  -> mandatory OTP or face liveness
* 81-100 -> block action, freeze session, alert fraud team, forensic snapshot
"""
from __future__ import annotations

import logging
from typing import Tuple

from config import get_settings
from models import ResponseAction, RiskBand

logger = logging.getLogger("trustiq.adaptive_auth")


class AdaptiveAuth:
    """Translate risk scores into authentication responses and bands."""

    def __init__(self) -> None:
        """Load risk thresholds from configuration."""
        s = get_settings()
        self.low = s.risk_threshold_low
        self.medium = s.risk_threshold_medium
        self.high = s.risk_threshold_high

    def band(self, risk_score: float) -> RiskBand:
        """Return the severity band for a score.

        Args:
            risk_score: The 0-100 risk score.

        Returns:
            The corresponding :class:`RiskBand`.
        """
        if risk_score <= self.low:
            return RiskBand.SAFE
        if risk_score <= self.medium:
            return RiskBand.ELEVATED
        if risk_score <= self.high:
            return RiskBand.HIGH
        return RiskBand.CRITICAL

    def decide(self, risk_score: float) -> Tuple[ResponseAction, str]:
        """Decide the response action for a given risk score.

        Args:
            risk_score: The 0-100 risk score.

        Returns:
            A tuple ``(response_action, human_message)``.
        """
        if risk_score <= self.low:
            action, msg = ResponseAction.SILENT_PASS, "Low risk: silent pass-through."
        elif risk_score <= self.medium:
            action, msg = (
                ResponseAction.PUSH_NOTIFICATION,
                "Elevated risk: push notification sent to trusted device.",
            )
        elif risk_score <= self.high:
            action, msg = (
                ResponseAction.STEP_UP_OTP,
                "High risk: mandatory OTP / face liveness required.",
            )
        else:
            action, msg = (
                ResponseAction.BLOCK,
                "Critical risk: action blocked, session frozen, fraud team alerted.",
            )
        logger.info("Adaptive auth score=%.0f action=%s", risk_score, action.value)
        return action, msg
