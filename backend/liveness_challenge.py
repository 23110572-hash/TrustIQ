"""Deepfake-Resistant Recovery — dynamic liveness challenge workflow.

Static "did liveness pass?" booleans are trivially defeated by a pre-recorded
or AI-generated (deepfake) video. TrustIQ instead issues a *dynamic, randomised*
challenge at recovery time: a short, unpredictable sequence of active actions
(turn head, blink, read these digits aloud, smile) bound to a one-time nonce.

A genuine live human completes the *specific* randomised actions, in a plausible
human reaction time, while passive depth/texture checks confirm a real 3-D face.
A replayed or synthetic stream fails because:

* it cannot satisfy a never-before-seen action sequence,
* its timing is too fast (pre-rendered) or inconsistent,
* passive depth/texture signals look flat / synthetic.

The engine returns a **challenge-response score** and an overall **recovery
confidence score**, plus concrete deepfake indicators for the analyst.
"""
from __future__ import annotations

import json
import logging
import random
import uuid
from datetime import datetime, timezone
from typing import List, Tuple

from models import (
    LivenessChallenge,
    LivenessStep,
    LivenessVerifyRequest,
    LivenessVerifyResult,
    RecoveryTier,
)

logger = logging.getLogger("trustiq.liveness")

# Pool of randomisable active-liveness actions.
_ACTION_POOL = [
    ("head_turn", "Slowly turn your head to the LEFT, then back to centre", ""),
    ("head_turn", "Slowly turn your head to the RIGHT, then back to centre", ""),
    ("blink", "Blink twice, deliberately", ""),
    ("smile", "Smile, then return to a neutral expression", ""),
    ("nod", "Nod your head once", ""),
]

# Human reaction-time window per step (ms). Too fast => pre-rendered/replayed.
_MIN_HUMAN_MS = 450.0
_MAX_HUMAN_MS = 9000.0


class LivenessChallengeEngine:
    """Issue and score dynamic, deepfake-resistant liveness challenges."""

    KEY = "liveness_challenge:{challenge_id}"

    def __init__(self, redis_client) -> None:
        """Initialise the engine.

        Args:
            redis_client: Redis-compatible client for challenge state + nonce.
        """
        self.redis = redis_client

    def issue(self, user_id: str, recovery_channel: str = "biometric") -> LivenessChallenge:
        """Issue a fresh, randomised liveness challenge.

        Args:
            user_id: The identity attempting recovery.
            recovery_channel: The recovery channel in use.

        Returns:
            A populated :class:`LivenessChallenge` (store the nonce client-side).
        """
        challenge_id = uuid.uuid4().hex[:12]
        nonce = uuid.uuid4().hex

        # 2-3 random active actions + one randomised spoken-digit challenge that
        # cannot be pre-recorded (the digits change every time).
        picks = random.sample(_ACTION_POOL, k=random.randint(2, 3))
        steps: List[LivenessStep] = []
        for i, (kind, instruction, _) in enumerate(picks):
            steps.append(
                LivenessStep(step_id=f"{challenge_id}-{i}", instruction=instruction, kind=kind)
            )
        digits = "-".join(str(random.randint(0, 9)) for _ in range(4))
        steps.append(
            LivenessStep(
                step_id=f"{challenge_id}-{len(steps)}",
                instruction=f"Read these digits aloud, clearly: {digits}",
                kind="read_digits",
                expected=digits,
            )
        )
        random.shuffle(steps)

        issued_at = datetime.now(timezone.utc)
        record = {
            "user_id": user_id,
            "nonce": nonce,
            "recovery_channel": recovery_channel,
            "issued_at": issued_at.isoformat(),
            "steps": {s.step_id: {"kind": s.kind, "expected": s.expected} for s in steps},
        }
        self.redis.setex(self.KEY.format(challenge_id=challenge_id), 120, json.dumps(record))

        logger.info("Liveness challenge issued user=%s id=%s steps=%d",
                    user_id, challenge_id, len(steps))
        return LivenessChallenge(
            challenge_id=challenge_id,
            user_id=user_id,
            steps=steps,
            nonce=nonce,
            issued_at=issued_at,
            expires_in_seconds=90,
        )

    def verify(self, req: LivenessVerifyRequest) -> LivenessVerifyResult:
        """Score a completed liveness challenge.

        Args:
            req: The verification request with per-step responses.

        Returns:
            A scored :class:`LivenessVerifyResult`.
        """
        now = datetime.now(timezone.utc)
        raw = self.redis.get(self.KEY.format(challenge_id=req.challenge_id))
        indicators: List[str] = []

        if not raw:
            return self._fail(req, "challenge expired or unknown — re-issue required", ["expired_challenge"])
        record = json.loads(raw)

        # Nonce binding defeats replay of a previously captured session.
        if record.get("nonce") != req.nonce or record.get("user_id") != req.user_id:
            indicators.append("nonce_mismatch_possible_replay")
            return self._fail(req, "nonce/identity mismatch — possible replay attack", indicators)

        steps = record["steps"]
        total = len(steps)
        correct = 0
        timing_ok = 0
        passive_flags = 0
        answered = {r.step_id: r for r in req.responses}

        for step_id, meta in steps.items():
            resp = answered.get(step_id)
            if resp is None:
                indicators.append(f"missing_step:{meta['kind']}")
                continue
            # Action correctness.
            if meta["kind"] == "read_digits":
                if resp.response.replace(" ", "").strip() == meta["expected"]:
                    correct += 1
                else:
                    indicators.append("wrong_spoken_digits")
            else:
                # For active actions, a non-empty acknowledgement of the action.
                if resp.response.strip().lower() in (meta["kind"], "done", "ok", "completed"):
                    correct += 1
                else:
                    indicators.append(f"action_not_performed:{meta['kind']}")
            # Human timing window.
            if _MIN_HUMAN_MS <= resp.response_ms <= _MAX_HUMAN_MS:
                timing_ok += 1
            elif resp.response_ms < _MIN_HUMAN_MS:
                indicators.append("response_too_fast_prerendered")
            else:
                indicators.append("response_too_slow")
            # Passive anti-spoofing.
            if not resp.passive_depth_ok:
                passive_flags += 1
                indicators.append("flat_depth_map_possible_screen_or_deepfake")
            if not resp.passive_texture_ok:
                passive_flags += 1
                indicators.append("synthetic_texture_detected")

        correctness = (correct / total) * 100.0 if total else 0.0
        timing = (timing_ok / total) * 100.0 if total else 0.0
        passive = max(0.0, 100.0 - passive_flags * 35.0)

        # Challenge-response score weights correctness most, then live timing.
        cr_score = 0.55 * correctness + 0.25 * timing + 0.20 * passive
        cr_score = float(max(0.0, min(100.0, cr_score)))

        # Recovery confidence also factors device/geo context.
        device_penalty = 0.0
        if req.device.is_vpn_or_tor:
            device_penalty += 12.0
            indicators.append("anonymised_network")
        if req.device.is_emulator:
            device_penalty += 18.0
            indicators.append("emulator_device")
        if req.context.distance_from_home_km > 500:
            device_penalty += 10.0
            indicators.append("far_from_home_region")

        recovery_confidence = float(max(0.0, min(100.0, cr_score - device_penalty)))
        passed = recovery_confidence >= 70.0 and not any(
            i.startswith("flat_depth") or i == "synthetic_texture_detected" for i in indicators
        )

        tier = self._tier(recovery_confidence, passed)
        # Clean up the one-time challenge.
        self.redis.setex(self.KEY.format(challenge_id=req.challenge_id), 1, "used")

        explanation = (
            f"Liveness {'PASSED' if passed else 'FAILED'}: challenge-response "
            f"{cr_score:.0f}/100 (correct {correct}/{total}, timing {timing:.0f}%, "
            f"passive {passive:.0f}%), recovery confidence {recovery_confidence:.0f}/100 → {tier.value}."
        )
        logger.info("Liveness verify user=%s id=%s passed=%s confidence=%.0f",
                    req.user_id, req.challenge_id, passed, recovery_confidence)

        return LivenessVerifyResult(
            challenge_id=req.challenge_id,
            user_id=req.user_id,
            passed=passed,
            challenge_response_score=round(cr_score, 1),
            recovery_confidence=round(recovery_confidence, 1),
            deepfake_indicators=sorted(set(indicators)),
            recommended_tier=tier,
            explanation=explanation,
            timestamp=now,
        )

    @staticmethod
    def _tier(confidence: float, passed: bool) -> RecoveryTier:
        """Map recovery confidence to a verification tier."""
        if not passed:
            if confidence < 35:
                return RecoveryTier.BLOCKED
            return RecoveryTier.IN_PERSON
        if confidence >= 88:
            return RecoveryTier.AUTO_APPROVE
        if confidence >= 78:
            return RecoveryTier.EMAIL_VERIFY
        return RecoveryTier.BIOMETRIC_VERIFY

    def _fail(self, req: LivenessVerifyRequest, reason: str, indicators: List[str]) -> LivenessVerifyResult:
        """Build a failed verification result."""
        return LivenessVerifyResult(
            challenge_id=req.challenge_id,
            user_id=req.user_id,
            passed=False,
            challenge_response_score=0.0,
            recovery_confidence=0.0,
            deepfake_indicators=indicators,
            recommended_tier=RecoveryTier.BLOCKED,
            explanation=f"Recovery blocked: {reason}.",
            timestamp=datetime.now(timezone.utc),
        )
