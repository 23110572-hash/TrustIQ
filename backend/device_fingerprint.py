"""Device fingerprinting module.

Extracts device attributes, matches them against a user's known trusted
devices, flags risky conditions (new device, emulator, VPN/Tor, spoofing) and
returns a device *trust* score in the range 0-1 (higher = more trusted).
"""
from __future__ import annotations

import json
import logging
from typing import List, Tuple

from models import DeviceSignal

logger = logging.getLogger("trustiq.device")


class DeviceFingerprinter:
    """Score devices against per-user trusted-device history."""

    DEVICES_KEY = "trusted_devices:{user_id}"

    def __init__(self, redis_client) -> None:
        """Initialise the fingerprinter.

        Args:
            redis_client: A Redis-compatible client storing trusted devices.
        """
        self.redis = redis_client

    def _composite_id(self, device: DeviceSignal) -> str:
        """Build a composite fingerprint from stable device attributes.

        Args:
            device: The device signal.

        Returns:
            A string fingerprint combining hardware/software attributes.
        """
        return "|".join(
            [
                device.device_id,
                device.os,
                device.browser,
                device.screen_resolution,
                device.webgl_hash,
            ]
        )

    def get_trusted_devices(self, user_id: str) -> List[str]:
        """Return the list of trusted device fingerprints for a user.

        Args:
            user_id: The user whose devices to fetch.

        Returns:
            A list of composite fingerprint strings.
        """
        raw = self.redis.get(self.DEVICES_KEY.format(user_id=user_id))
        if raw:
            try:
                return list(json.loads(raw))
            except (ValueError, TypeError):
                logger.warning("Corrupt device list for %s", user_id)
        return []

    def register_device(self, user_id: str, fingerprint: str) -> None:
        """Add a fingerprint to the user's trusted device list.

        Args:
            user_id: The user to update.
            fingerprint: The composite fingerprint to register.
        """
        devices = self.get_trusted_devices(user_id)
        if fingerprint not in devices:
            devices.append(fingerprint)
            # Keep only the 10 most-recent trusted devices.
            devices = devices[-10:]
            self.redis.setex(
                self.DEVICES_KEY.format(user_id=user_id),
                86400 * 90,
                json.dumps(devices),
            )

    def score(self, user_id: str, device: DeviceSignal) -> Tuple[float, List[str], str]:
        """Return a device trust score and risk flags.

        Args:
            user_id: The user performing the action.
            device: The device signal to evaluate.

        Returns:
            A tuple ``(trust_score, flags, explanation)`` where trust_score is
            0-1 (higher = more trusted).
        """
        fingerprint = self._composite_id(device)
        trusted = self.get_trusted_devices(user_id)
        flags: List[str] = []

        trust = 1.0
        is_known = fingerprint in trusted

        if not is_known:
            trust -= 0.5
            flags.append("new_device")

        if device.is_emulator:
            trust -= 0.4
            flags.append("emulator_detected")

        if device.is_vpn_or_tor:
            trust -= 0.3
            flags.append("vpn_or_tor")

        # Spoofing heuristic: impossible / inconsistent attribute combos.
        if device.screen_resolution == "0x0" or device.os == "unknown":
            trust -= 0.2
            flags.append("possible_spoofing")

        trust = float(max(0.0, min(1.0, trust)))

        # Register devices that look legitimate (new but no hard-fraud flags),
        # so a genuine device becomes trusted after its first clean use.
        hard_flags = {"emulator_detected", "vpn_or_tor", "possible_spoofing"}
        if not hard_flags.intersection(flags):
            self.register_device(user_id, fingerprint)

        explanation = (
            f"device {'known' if is_known else 'NEW'}; flags={flags or 'none'}"
        )
        logger.info("Device trust user=%s trust=%.2f flags=%s", user_id, trust, flags)
        return trust, flags, explanation
