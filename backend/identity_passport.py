"""Identity Passport — the persistent digital identity profile.

Traditional authentication verifies identity *once*. The Identity Passport is
the durable record TrustIQ continuously validates *against*. For every customer
and employee it remembers:

* trusted devices and trusted locations,
* a behavioural baseline reference,
* trust history and trend,
* recovery history, KYC / verification history,
* fraud exposure.

Every banking event is compared to the passport to produce an **Identity Match
Score (0-100)** — "how much does this event look like the real person?".

The passport is stored in Redis (with the in-memory MockRedis fallback) so it
survives across sessions and channels, which is what makes trust *continuous*
rather than per-login.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from models import (
    BehavioralSignal,
    ContextSignal,
    DeviceSignal,
    IdentityMatch,
)
from privacy_layer import mask_user_id

logger = logging.getLogger("trustiq.passport")


class IdentityPassport:
    """Durable per-identity profile with Identity-Match scoring."""

    KEY = "identity_passport:{user_id}"
    _MAX_DEVICES = 10
    _MAX_LOCATIONS = 12
    _MAX_HOURS = 48

    def __init__(self, redis_client) -> None:
        """Initialise the passport store.

        Args:
            redis_client: Redis-compatible client used for durable storage.
        """
        self.redis = redis_client

    # ------------------------------------------------------------------ #
    # Storage
    # ------------------------------------------------------------------ #
    def _blank(self, user_id: str, is_employee: bool) -> Dict[str, Any]:
        """Return a fresh passport document for a new identity.

        Args:
            user_id: The identity the passport belongs to.
            is_employee: Whether the identity is a bank employee.

        Returns:
            A new passport dictionary.
        """
        return {
            "user_id": user_id,
            "is_employee": is_employee,
            "trusted_devices": [],
            "trusted_locations": [],
            "active_hours": [],
            "event_count": 0,
            "kyc_verified": False,
            "recovery_attempts": 0,
            "fraud_exposure": 0.0,
            "first_seen": datetime.now(timezone.utc).isoformat(),
            "last_seen": None,
        }

    def load(self, user_id: str, is_employee: bool = False) -> Dict[str, Any]:
        """Load a passport, creating a blank one if none exists.

        Args:
            user_id: The identity to load.
            is_employee: Whether the identity is an employee (new passports).

        Returns:
            The passport document.
        """
        raw = self.redis.get(self.KEY.format(user_id=user_id))
        if raw:
            try:
                return json.loads(raw)
            except (ValueError, TypeError):
                logger.warning("Corrupt passport for %s; recreating.", user_id)
        return self._blank(user_id, is_employee)

    def save(self, passport: Dict[str, Any]) -> None:
        """Persist a passport document.

        Args:
            passport: The passport dictionary to store.
        """
        self.redis.setex(
            self.KEY.format(user_id=passport["user_id"]),
            86400 * 180,
            json.dumps(passport),
        )

    # ------------------------------------------------------------------ #
    # Matching
    # ------------------------------------------------------------------ #
    @staticmethod
    def _device_key(device: DeviceSignal) -> str:
        """Build a stable device key for passport membership checks."""
        return f"{device.device_id}|{device.os}|{device.webgl_hash}"

    def match(
        self,
        user_id: str,
        device: DeviceSignal,
        context: ContextSignal,
        behavioral_anomaly: float,
        is_employee: bool = False,
    ) -> IdentityMatch:
        """Score how well an event matches the stored Identity Passport.

        Args:
            user_id: The identity being evaluated.
            device: The device used for the event.
            context: The event context (location, time).
            behavioral_anomaly: Behavioural anomaly 0-1 (1 = very different).
            is_employee: Whether the identity is an employee.

        Returns:
            A populated :class:`IdentityMatch`.
        """
        passport = self.load(user_id, is_employee)
        is_new_identity = passport["event_count"] == 0

        device_match = self._device_key(device) in passport["trusted_devices"]
        location_match = (
            context.city in passport["trusted_locations"]
            or not passport["trusted_locations"]
        )
        time_match = (
            context.hour_of_day in passport["active_hours"]
            or not passport["active_hours"]
        )
        behavioral_match = float(max(0.0, 1.0 - behavioral_anomaly))

        # Weighted identity-match score (higher = more like the real person).
        # New identities get a neutral 60 so onboarding is not penalised as a
        # mismatch — there is simply nothing to match against yet.
        if is_new_identity:
            score = 60.0
            detail = "new identity — passport is being established"
        else:
            score = (
                (35.0 if device_match else 0.0)
                + (20.0 if location_match else 0.0)
                + (behavioral_match * 30.0)
                + (15.0 if time_match else 0.0)
            )
            parts = []
            parts.append("known device" if device_match else "UNKNOWN device")
            parts.append("known location" if location_match else "new location")
            parts.append(f"behaviour {behavioral_match * 100:.0f}% match")
            parts.append("typical hour" if time_match else "off-pattern hour")
            detail = ", ".join(parts)

        return IdentityMatch(
            identity_match_score=round(float(max(0.0, min(100.0, score))), 2),
            device_match=device_match,
            location_match=location_match,
            behavioral_match=round(behavioral_match, 2),
            time_pattern_match=time_match,
            detail=detail,
        )

    # ------------------------------------------------------------------ #
    # Learning
    # ------------------------------------------------------------------ #
    def observe(
        self,
        user_id: str,
        device: DeviceSignal,
        context: ContextSignal,
        risk_score: float,
        is_employee: bool = False,
        event_kind: str = "event",
    ) -> Dict[str, Any]:
        """Update the passport from an observed event.

        Trusted attributes are only *learned* from low-risk events so an
        attacker cannot teach the passport their device. Recovery and fraud
        history are always recorded.

        Args:
            user_id: The identity to update.
            device: The device used.
            context: The event context.
            risk_score: The event's risk score (gates learning).
            is_employee: Whether the identity is an employee.
            event_kind: A label for the event (e.g. "recovery", "kyc").

        Returns:
            The updated passport document.
        """
        passport = self.load(user_id, is_employee)
        passport["event_count"] += 1
        passport["last_seen"] = datetime.now(timezone.utc).isoformat()

        if event_kind == "recovery":
            passport["recovery_attempts"] += 1
        if event_kind == "kyc":
            passport["kyc_verified"] = True

        # Only low-risk events teach trusted attributes.
        if risk_score <= 40:
            dkey = self._device_key(device)
            if dkey not in passport["trusted_devices"]:
                passport["trusted_devices"] = (
                    passport["trusted_devices"] + [dkey]
                )[-self._MAX_DEVICES :]
            if context.city and context.city != "unknown":
                if context.city not in passport["trusted_locations"]:
                    passport["trusted_locations"] = (
                        passport["trusted_locations"] + [context.city]
                    )[-self._MAX_LOCATIONS :]
            if context.hour_of_day not in passport["active_hours"]:
                passport["active_hours"] = (
                    passport["active_hours"] + [context.hour_of_day]
                )[-self._MAX_HOURS :]
        elif risk_score >= 80:
            # A critical event raises the identity's fraud exposure.
            passport["fraud_exposure"] = min(
                100.0, passport["fraud_exposure"] + 20.0
            )

        self.save(passport)
        return passport

    def all_passports(self) -> List[Dict[str, Any]]:
        """Return every stored passport (for dashboards / compliance).

        Returns:
            A list of passport documents.
        """
        out: List[Dict[str, Any]] = []
        for key in self.redis.keys(self.KEY.format(user_id="*")):
            raw = self.redis.get(key)
            if raw:
                try:
                    out.append(json.loads(raw))
                except (ValueError, TypeError):
                    continue
        return out
