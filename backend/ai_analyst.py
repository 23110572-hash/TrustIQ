"""AI Fraud Analyst — explainable, never a black box.

Every TrustIQ decision is accompanied by an analyst-style write-up: a headline,
a plain-English narrative, the concrete contributing factors, an investigation
summary and a recommended action — plus a confidence value.

The goal is the example from the brief:

    "This login attempt is considered high risk because the user is accessing
     from a previously unseen Android device, behavioural similarity dropped
     from 92% to 41%, and the session originated 500km from the user's normal
     operating region."

This module is deterministic and rule-grounded (no opaque generation): every
sentence is traceable to a numeric signal, which is exactly what a regulator
and a fraud-ops team need.
"""
from __future__ import annotations

import logging
from typing import List

from models import (
    AIInsight,
    Channel,
    DeviceSignal,
    IdentityMatch,
    ResponseAction,
    TrustEventType,
)

logger = logging.getLogger("trustiq.ai_analyst")

_CHANNEL_PHRASE = {
    Channel.MOBILE_BANKING: "the bob World mobile app",
    Channel.INTERNET_BANKING: "internet banking",
    Channel.UPI: "a UPI payment flow",
    Channel.BRANCH: "a branch / CBS terminal",
    Channel.EMPLOYEE_PORTAL: "the internal employee portal",
    Channel.CALL_CENTER: "the call-centre channel",
    Channel.ATM: "an ATM",
}

_EVENT_PHRASE = {
    TrustEventType.LOGIN: "a sign-in",
    TrustEventType.TRANSFER: "a money transfer",
    TrustEventType.OTP: "an OTP request",
    TrustEventType.PROFILE_CHANGE: "a profile change",
    TrustEventType.ACCOUNT_RECOVERY: "an account-recovery attempt",
    TrustEventType.BENEFICIARY_ADD: "a new beneficiary addition",
    TrustEventType.DEVICE_CHANGE: "a device change",
    TrustEventType.SETTINGS_CHANGE: "a security-settings change",
    TrustEventType.KYC_ONBOARDING: "a new-account onboarding",
    TrustEventType.EMPLOYEE_ACCESS: "a privileged data access",
    TrustEventType.NAVIGATION: "an in-session navigation event",
}


class AIFraudAnalyst:
    """Compose explainable analyst narratives for trust decisions."""

    def analyse(
        self,
        *,
        channel: Channel,
        event_type: TrustEventType,
        risk_score: float,
        trust_score: float,
        identity_match: IdentityMatch,
        device: DeviceSignal,
        device_flags: List[str],
        distance_km: float,
        amount: float,
        beneficiary_flags: List[str],
        fraud_links: float,
        action: ResponseAction,
        confidence: float,
    ) -> AIInsight:
        """Produce an explainable insight for a trust decision.

        Args:
            channel: Originating channel.
            event_type: The business event type.
            risk_score: Event risk 0-100.
            trust_score: Persistent identity trust 0-100.
            identity_match: Identity-match result.
            device: The device used.
            device_flags: Device risk flags.
            distance_km: Distance from home region.
            amount: Transaction amount.
            beneficiary_flags: Beneficiary risk flags.
            fraud_links: Identity-graph fraud-ring score 0-100.
            action: The chosen adaptive-auth action.
            confidence: Decision confidence 0-1.

        Returns:
            A populated :class:`AIInsight`.
        """
        reasons: List[str] = []

        if not identity_match.device_match and "new_device" in device_flags:
            os_label = device.os if device.os != "unknown" else "an unrecognised"
            reasons.append(f"the access came from a previously unseen {os_label} device")
        if identity_match.behavioral_match < 0.6:
            reasons.append(
                f"behavioural similarity fell to {identity_match.behavioral_match * 100:.0f}% "
                f"of the customer's baseline"
            )
        if distance_km > 300:
            reasons.append(
                f"the session originated ~{distance_km:.0f} km from the customer's normal region"
            )
        if "vpn_or_tor" in device_flags:
            reasons.append("the connection was anonymised through VPN/Tor")
        if "emulator_detected" in device_flags:
            reasons.append("the device appears to be an emulator")
        if "possible_spoofing" in device_flags:
            reasons.append("device attributes look spoofed or inconsistent")
        if amount >= 25000:
            reasons.append(f"a high-value amount of ₹{amount:,.0f} was involved")
        for bf in beneficiary_flags:
            if "mule_fan_in" in bf:
                n = bf.split("_")[3] if len(bf.split("_")) > 3 else "several"
                reasons.append(f"the payee is receiving funds from {n} unrelated senders (mule fan-in)")
            elif bf == "new_beneficiary_large_transfer":
                reasons.append("a large transfer was sent to a beneficiary added moments earlier")
        if fraud_links >= 50:
            reasons.append("the identity is linked to a known fraud ring via shared devices/IPs")
        if not reasons:
            reasons.append(
                "all signals are consistent with the customer's established Identity Passport"
            )

        # Severity wording from the action that was taken.
        severity = {
            ResponseAction.SILENT_PASS: "low risk",
            ResponseAction.PUSH_NOTIFICATION: "slightly elevated risk",
            ResponseAction.STEP_UP_OTP: "high risk",
            ResponseAction.BLOCK: "critical risk",
        }[action]

        channel_p = _CHANNEL_PHRASE.get(channel, "a banking channel")
        event_p = _EVENT_PHRASE.get(event_type, "an event")

        headline = (
            f"{event_p.capitalize()} on {channel_p} assessed as {severity} "
            f"(trust {trust_score:.0f}/100, risk {risk_score:.0f}/100)"
        )

        narrative = (
            f"This {event_p} on {channel_p} is considered {severity} because "
            + _join_reasons(reasons)
            + "."
        )

        investigation_summary = self._investigation(action, reasons, identity_match, fraud_links)
        recommended = self._recommended(action)

        return AIInsight(
            headline=headline,
            narrative=narrative,
            contributing_factors=reasons,
            investigation_summary=investigation_summary,
            recommended_action=recommended,
            confidence=round(float(confidence), 2),
        )

    @staticmethod
    def _investigation(
        action: ResponseAction,
        reasons: List[str],
        identity_match: IdentityMatch,
        fraud_links: float,
    ) -> str:
        """Compose a concise investigation summary for fraud ops.

        Args:
            action: The chosen action.
            reasons: The contributing reasons.
            identity_match: The identity-match result.
            fraud_links: Fraud-ring score.

        Returns:
            A short investigation paragraph.
        """
        if action == ResponseAction.SILENT_PASS:
            return (
                "No investigation required. Identity match "
                f"{identity_match.identity_match_score:.0f}/100; allowed silently "
                "and the Identity Passport was reinforced."
            )
        if action == ResponseAction.PUSH_NOTIFICATION:
            return (
                "Soft confirmation pushed to the customer's trusted device. If the "
                "customer declines or does not respond, escalate to step-up auth."
            )
        if action == ResponseAction.STEP_UP_OTP:
            return (
                "Step-up verification enforced (OTP / face liveness). Review the "
                f"{len(reasons)} divergent signal(s) above; confirm the device and "
                "location with the customer before clearing."
            )
        # BLOCK
        ring = " The identity also shows fraud-ring linkage." if fraud_links >= 50 else ""
        return (
            "Action blocked and session frozen. Treat as a probable account-takeover "
            f"/ fraud attempt and open a case.{ring} Recommend contacting the customer "
            "on a verified channel and reviewing recent device and beneficiary changes."
        )

    @staticmethod
    def _recommended(action: ResponseAction) -> str:
        """Map an action to a recommended next step.

        Args:
            action: The chosen action.

        Returns:
            A short recommendation string.
        """
        return {
            ResponseAction.SILENT_PASS: "Allow — no friction.",
            ResponseAction.PUSH_NOTIFICATION: "Confirm via trusted-device push.",
            ResponseAction.STEP_UP_OTP: "Require OTP / face liveness before proceeding.",
            ResponseAction.BLOCK: "Block, freeze session and alert the fraud team.",
        }[action]


def _join_reasons(reasons: List[str]) -> str:
    """Join reason clauses into a natural-language list.

    Args:
        reasons: The reason clauses.

    Returns:
        A grammatically joined string.
    """
    if len(reasons) == 1:
        return reasons[0]
    if len(reasons) == 2:
        return f"{reasons[0]} and {reasons[1]}"
    return ", ".join(reasons[:-1]) + f", and {reasons[-1]}"
