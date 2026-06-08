"""Identity Trust Engine — the heart of continuous trust.

Every customer and employee carries a single, persistent **Trust Score (0-100)**
that *evolves over time*. Unlike a risk score (which describes one event), the
trust score is a memory: it rewards consistent, recognisable behaviour and
decays sharply when an identity does something that looks like compromise.

Trust is a function of signals drawn from the rest of the platform:

    behavioural consistency · trusted devices · location history ·
    transaction patterns · onboarding history · recovery history ·
    fraud links · session trust · insider risk

The engine keeps a rolling **trust history** and derives a **trend**
(rising / falling / stable) so the dashboard can show identities gaining or
losing trust through their journey — the core "continuous identity" idea.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Dict, List, Tuple

from models import IdentityMatch, TrustBand, TrustFactor

logger = logging.getLogger("trustiq.identity_trust")

# Starting trust for a brand-new identity: neutral, must be earned.
_SEED_TRUST = 55.0
# How many history points to retain per identity.
_HISTORY_LEN = 60


class IdentityTrustEngine:
    """Maintain a persistent, evolving trust score per identity."""

    KEY = "identity_trust:{user_id}"

    def __init__(self, redis_client) -> None:
        """Initialise the trust engine.

        Args:
            redis_client: Redis-compatible client for durable trust storage.
        """
        self.redis = redis_client

    # ------------------------------------------------------------------ #
    # Storage
    # ------------------------------------------------------------------ #
    def _load(self, user_id: str) -> Dict:
        """Load the stored trust state for an identity.

        Args:
            user_id: The identity to load.

        Returns:
            A trust-state dict ``{score, history:[...]}``.
        """
        raw = self.redis.get(self.KEY.format(user_id=user_id))
        if raw:
            try:
                return json.loads(raw)
            except (ValueError, TypeError):
                logger.warning("Corrupt trust state for %s; reseeding.", user_id)
        return {"score": _SEED_TRUST, "history": []}

    def _save(self, user_id: str, state: Dict) -> None:
        """Persist the trust state for an identity.

        Args:
            user_id: The identity to save.
            state: The trust-state dict.
        """
        self.redis.setex(self.KEY.format(user_id=user_id), 86400 * 180, json.dumps(state))

    def current(self, user_id: str) -> float:
        """Return the current persistent trust score for an identity.

        Args:
            user_id: The identity to query.

        Returns:
            The current trust score (0-100).
        """
        return float(self._load(user_id)["score"])

    # ------------------------------------------------------------------ #
    # Scoring
    # ------------------------------------------------------------------ #
    @staticmethod
    def band(trust: float) -> TrustBand:
        """Map a trust score to a :class:`TrustBand`.

        Args:
            trust: The 0-100 trust score.

        Returns:
            The corresponding band.
        """
        if trust >= 80:
            return TrustBand.VERIFIED
        if trust >= 60:
            return TrustBand.ESTABLISHED
        if trust >= 40:
            return TrustBand.GUARDED
        if trust >= 20:
            return TrustBand.UNTRUSTED
        return TrustBand.COMPROMISED

    def _factors(
        self,
        risk_score: float,
        identity_match: IdentityMatch,
        device_trust: float,
        fraud_links: float,
        session_trust: float,
        insider_risk: float,
        is_employee: bool,
    ) -> List[TrustFactor]:
        """Build the explainable per-factor trust breakdown.

        Args:
            risk_score: Event risk score (0-100).
            identity_match: Identity-match result.
            device_trust: Device trust 0-1.
            fraud_links: Identity-graph fraud-ring score 0-100.
            session_trust: Current session trust 0-100.
            insider_risk: Insider/UEBA risk 0-100 (employees only).
            is_employee: Whether the identity is an employee.

        Returns:
            A list of :class:`TrustFactor`.
        """
        factors = [
            TrustFactor(
                name="identity_match",
                score=round(identity_match.identity_match_score, 1),
                weight=0.30,
                direction="raises" if identity_match.identity_match_score >= 60 else "lowers",
                detail=identity_match.detail,
            ),
            TrustFactor(
                name="trusted_device",
                score=round(device_trust * 100.0, 1),
                weight=0.18,
                direction="raises" if device_trust >= 0.6 else "lowers",
                detail="recognised device" if identity_match.device_match else "unrecognised device",
            ),
            TrustFactor(
                name="behavioural_consistency",
                score=round(identity_match.behavioral_match * 100.0, 1),
                weight=0.17,
                direction="raises" if identity_match.behavioral_match >= 0.6 else "lowers",
                detail=f"behaviour {identity_match.behavioral_match * 100:.0f}% match to baseline",
            ),
            TrustFactor(
                name="transaction_pattern",
                score=round(100.0 - risk_score, 1),
                weight=0.20,
                direction="raises" if risk_score <= 40 else "lowers",
                detail=f"event risk {risk_score:.0f}/100",
            ),
            TrustFactor(
                name="fraud_links",
                score=round(100.0 - fraud_links, 1),
                weight=0.10,
                direction="lowers" if fraud_links > 0 else "neutral",
                detail=f"identity-graph fraud links score {fraud_links:.0f}",
            ),
            TrustFactor(
                name="session_trust",
                score=round(session_trust, 1),
                weight=0.05,
                direction="raises" if session_trust >= 60 else "lowers",
                detail=f"live session trust {session_trust:.0f}/100",
            ),
        ]
        if is_employee:
            factors.append(
                TrustFactor(
                    name="insider_risk",
                    score=round(100.0 - insider_risk, 1),
                    weight=0.15,
                    direction="lowers" if insider_risk > 30 else "neutral",
                    detail=f"privileged-access risk {insider_risk:.0f}/100",
                )
            )
        return factors

    def update(
        self,
        user_id: str,
        risk_score: float,
        identity_match: IdentityMatch,
        device_trust: float,
        fraud_links: float,
        session_trust: float,
        trigger: str,
        channel: str = "",
        insider_risk: float = 0.0,
        is_employee: bool = False,
    ) -> Tuple[float, TrustBand, str, List[TrustFactor]]:
        """Evolve an identity's trust score from a new event.

        The new trust is a blend of the *target* trust implied by the current
        evidence (the weighted factor score) and the identity's *prior* trust,
        with asymmetric inertia: trust is slow to earn and fast to lose, exactly
        like a human risk analyst's confidence.

        Args:
            user_id: The identity to update.
            risk_score: The event risk score 0-100.
            identity_match: The identity-match result.
            device_trust: Device trust 0-1.
            fraud_links: Identity-graph fraud-ring score 0-100.
            session_trust: Current session trust 0-100.
            trigger: A short label describing what drove the change.
            channel: The originating channel.
            insider_risk: Insider risk 0-100 (employees only).
            is_employee: Whether the identity is an employee.

        Returns:
            ``(trust_score, trust_band, trust_trend, factors)``.
        """
        state = self._load(user_id)
        prior = float(state["score"])

        factors = self._factors(
            risk_score, identity_match, device_trust, fraud_links,
            session_trust, insider_risk, is_employee,
        )
        total_weight = sum(f.weight for f in factors) or 1.0
        target = sum(f.score * f.weight for f in factors) / total_weight

        # Asymmetric inertia: rise gently (alpha 0.25), fall fast (alpha 0.6).
        # A critical event (risk >= 80) applies an extra hard penalty so a clear
        # takeover collapses trust immediately.
        if target >= prior:
            alpha = 0.25
        else:
            alpha = 0.60
        new_trust = prior + alpha * (target - prior)
        if risk_score >= 80:
            new_trust -= 20.0
        if fraud_links >= 50:
            new_trust -= 10.0
        new_trust = float(max(0.0, min(100.0, new_trust)))

        now = datetime.now(timezone.utc)
        history = state["history"]
        history.append(
            {
                "timestamp": now.isoformat(),
                "trust_score": round(new_trust, 2),
                "trigger": trigger,
                "channel": channel,
            }
        )
        history = history[-_HISTORY_LEN:]
        self._save(user_id, {"score": new_trust, "history": history})

        trend = self._trend(history)
        return round(new_trust, 2), self.band(new_trust), trend, factors

    @staticmethod
    def _trend(history: List[Dict]) -> str:
        """Derive a rising/falling/stable trend from recent history.

        Args:
            history: The trust history points.

        Returns:
            One of ``"rising"``, ``"falling"`` or ``"stable"``.
        """
        if len(history) < 3:
            return "stable"
        recent = [h["trust_score"] for h in history[-5:]]
        delta = recent[-1] - recent[0]
        if delta > 3:
            return "rising"
        if delta < -3:
            return "falling"
        return "stable"

    def history(self, user_id: str) -> List[Dict]:
        """Return the trust history for an identity.

        Args:
            user_id: The identity to query.

        Returns:
            The list of trust-history points (oldest first).
        """
        return self._load(user_id)["history"]
