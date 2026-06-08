"""Trust Orchestrator — the single brain behind `POST /api/trust/evaluate`.

This is what turns a *collection of security modules* into one **Continuous
Identity Trust Platform**. For any event, on any channel, it:

1. scores real-time **risk** (reusing the ML risk engine),
2. compares the event to the customer's **Identity Passport** (match score),
3. evolves the persistent **Identity Trust Score**,
4. scores the **beneficiary** (for transfers),
5. tracks **continuous session trust** (trust rises/falls *within* a session),
6. asks the **AI Fraud Analyst** for an explainable verdict,

and returns one unified, fully-explainable :class:`TrustEvaluation`.

The decision is *trust-aware*: a high persistent trust softens borderline
friction for genuine customers, while low trust or fraud-ring links harden it —
which is exactly the friction-optimised behaviour the brief asks for.
"""
from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import List, Tuple

from adaptive_auth import AdaptiveAuth
from ai_analyst import AIFraudAnalyst
from beneficiary_trust import BeneficiaryTrustEngine
from channel_trust import ChannelTrustTracker
from config import get_settings
from identity_passport import IdentityPassport
from identity_trust import IdentityTrustEngine
from impossible_travel import ImpossibleTravelDetector
from models import (
    TRUST_EVENT_TO_ACTION,
    BankingEvent,
    GraphEdge,
    GraphNode,
    GraphView,
    ImpossibleTravelResult,
    IdentityPassportView,
    ResponseAction,
    TrustBand,
    TrustEvaluation,
    TrustEvaluationRequest,
    TrustFactor,
    TrustHistoryPoint,
)
from privacy_layer import mask_user_id
from risk_engine import RiskEngine

logger = logging.getLogger("trustiq.orchestrator")

# How much each in-session sensitive event erodes session trust.
_SESSION_PENALTY = {
    "beneficiary_add": 18.0,
    "transfer": 10.0,
    "profile_change": 14.0,
    "settings_change": 16.0,
    "device_change": 20.0,
    "account_recovery": 22.0,
}


class TrustOrchestrator:
    """Fuse all engines into one continuous, explainable trust decision."""

    SESSION_KEY = "session_trust:{session_id}"

    def __init__(self, redis_client, risk_engine: RiskEngine, compliance=None) -> None:
        """Wire the orchestrator to the shared engines.

        Args:
            redis_client: Redis-compatible client.
            risk_engine: The shared risk engine (also owns the identity graph).
            compliance: Optional ComplianceCenter for explainability accounting.
        """
        self.redis = redis_client
        self.settings = get_settings()
        self.risk = risk_engine
        self.passport = IdentityPassport(redis_client)
        self.trust = IdentityTrustEngine(redis_client)
        self.beneficiary = BeneficiaryTrustEngine(redis_client, risk_engine.identity)
        self.analyst = AIFraudAnalyst()
        self.auth = AdaptiveAuth()
        self.travel = ImpossibleTravelDetector(redis_client)
        self.channels = ChannelTrustTracker(redis_client)
        self.compliance = compliance
        # Capture the impossible-travel result of the most recent evaluation so
        # the API layer can raise a dedicated alert.
        self.last_travel: ImpossibleTravelResult | None = None

    # ------------------------------------------------------------------ #
    # Session trust
    # ------------------------------------------------------------------ #
    def _session_trust(self, session_id: str, event_type: str, risk_score: float) -> float:
        """Update and return the continuous trust for a live session.

        Session trust starts high and erodes as sensitive in-session actions
        pile up or risk rises — modelling the brief's requirement that trust
        "dynamically rise and fall throughout the session" rather than being
        frozen at login.

        Args:
            session_id: The session identifier.
            event_type: The current event type.
            risk_score: The current event's risk score.

        Returns:
            The updated session-trust score 0-100.
        """
        key = self.SESSION_KEY.format(session_id=session_id)
        raw = self.redis.get(key)
        score = float(json.loads(raw)["score"]) if raw else 88.0

        penalty = _SESSION_PENALTY.get(event_type, 4.0)
        score -= penalty * (risk_score / 100.0) * 2.0
        # Calm, low-risk activity slowly restores session trust.
        if risk_score <= 25:
            score += 3.0
        score = float(max(0.0, min(100.0, score)))
        self.redis.setex(key, 1800, json.dumps({"score": score}))
        return round(score, 2)

    # ------------------------------------------------------------------ #
    # Main entry point
    # ------------------------------------------------------------------ #
    def evaluate(self, req: TrustEvaluationRequest) -> TrustEvaluation:
        """Evaluate any event on any channel and return a unified verdict.

        Args:
            req: The unified trust-evaluation request.

        Returns:
            A fully-populated, explainable :class:`TrustEvaluation`.
        """
        now = datetime.now(timezone.utc)
        action_type = TRUST_EVENT_TO_ACTION[req.event_type]
        session_id = req.session_id or f"{req.user_id}:default"

        # 1. Real-time ML risk (also updates identity graph + sequence + audit).
        banking_event = BankingEvent(
            user_id=req.user_id,
            action=action_type,
            behavioral=req.behavioral,
            device=req.device,
            context=req.context,
        )
        risk_resp, detail = self.risk.evaluate_detailed(banking_event)
        risk_score = risk_resp.risk_score

        # 1b. Impossible-travel detection (geo-velocity since last event).
        travel = self.travel.evaluate(req.user_id, req.context)
        self.last_travel = travel
        if travel.impossible:
            risk_score = min(100.0, risk_score + travel.risk_boost)
            detail.setdefault("device_flags", []).append("impossible_travel")

        # 2. Identity Passport match.
        identity_match = self.passport.match(
            user_id=req.user_id,
            device=req.device,
            context=req.context,
            behavioral_anomaly=detail["behavioral_anomaly"],
            is_employee=req.is_employee,
        )

        # 3. Beneficiary trust (transfers / beneficiary adds only).
        beneficiary_trust = None
        beneficiary_flags: List[str] = []
        if req.beneficiary is not None:
            beneficiary_trust, beneficiary_flags, _ = self.beneficiary.evaluate(
                req.user_id, req.beneficiary, req.context
            )
            # A risky payee lifts the event risk.
            if beneficiary_trust < 50:
                risk_score = min(100.0, risk_score + (50 - beneficiary_trust) * 0.6)

        # 4. Continuous session trust.
        session_trust = self._session_trust(session_id, req.event_type.value, risk_score)

        # 5. Evolve persistent identity trust.
        trust_score, trust_band, trust_trend, trust_factors = self.trust.update(
            user_id=req.user_id,
            risk_score=risk_score,
            identity_match=identity_match,
            device_trust=detail["device_trust"],
            fraud_links=detail["fraud_links"],
            session_trust=session_trust,
            trigger=req.event_type.value,
            channel=req.channel.value,
            insider_risk=0.0,
            is_employee=False,
        )

        # 6. Trust-aware decision: blend event risk with the inverse of trust so
        #    a strongly-trusted identity gets less friction on a borderline event
        #    and a low-trust identity gets more.
        effective_risk = self._effective_risk(risk_score, trust_score, detail["fraud_links"])
        action, message = self.auth.decide(effective_risk)
        risk_band = self.auth.band(effective_risk)

        # 7. Learn: reinforce the passport from this (now fully scored) event.
        self.passport.observe(
            user_id=req.user_id,
            device=req.device,
            context=req.context,
            risk_score=effective_risk,
            is_employee=req.is_employee,
            event_kind="recovery" if req.event_type.value == "account_recovery" else "event",
        )

        # 8. Explainable AI analyst verdict.
        ai_insight = self.analyst.analyse(
            channel=req.channel,
            event_type=req.event_type,
            risk_score=effective_risk,
            trust_score=trust_score,
            identity_match=identity_match,
            device=req.device,
            device_flags=detail["device_flags"],
            distance_km=req.context.distance_from_home_km,
            amount=req.context.amount,
            beneficiary_flags=beneficiary_flags,
            fraud_links=detail["fraud_links"],
            action=action,
            confidence=risk_resp.confidence,
        )

        # Merge the trust factors with the event-risk factors for transparency.
        factors = trust_factors + [
            TrustFactor(
                name=f.name,
                score=f.score,
                weight=f.weight,
                direction="lowers" if f.score >= 50 else "neutral",
                detail=f.detail,
            )
            for f in risk_resp.factors
        ]

        # Surface impossible travel explicitly in the explanation + factors.
        if travel.impossible:
            ai_insight.contributing_factors.insert(0, travel.detail)
            factors.insert(
                0,
                TrustFactor(
                    name="impossible_travel",
                    score=round(travel.risk_boost / 45.0 * 100.0, 1),
                    weight=0.0,
                    direction="lowers",
                    detail=travel.detail,
                ),
            )

        explanation = ai_insight.narrative

        # Per-channel trust signal + compliance explainability accounting.
        self.channels.record(req.channel, trust_score, effective_risk, action.value)
        if self.compliance is not None:
            self.compliance.note_explainable_decision()

        logger.info(
            "TRUST user=%s channel=%s event=%s trust=%.0f match=%.0f risk=%.0f action=%s",
            mask_user_id(req.user_id), req.channel.value, req.event_type.value,
            trust_score, identity_match.identity_match_score, effective_risk, action.value,
        )

        return TrustEvaluation(
            request_id=str(uuid.uuid4())[:12],
            user_id=req.user_id,
            channel=req.channel,
            event_type=req.event_type,
            trust_score=trust_score,
            trust_band=trust_band,
            trust_trend=trust_trend,
            identity_match_score=identity_match.identity_match_score,
            risk_score=round(effective_risk, 2),
            risk_band=risk_band,
            confidence=risk_resp.confidence,
            session_trust=session_trust,
            beneficiary_trust=beneficiary_trust,
            action=action,
            explanation=explanation,
            factors=factors,
            ai_insight=ai_insight,
            model_version=self.settings.model_version,
            timestamp=now,
        )

    # ------------------------------------------------------------------ #
    # Read models for the Command Center
    # ------------------------------------------------------------------ #
    def trust_history(self, user_id: str) -> List[TrustHistoryPoint]:
        """Return an identity's trust-score history as typed points.

        Args:
            user_id: The identity to query.

        Returns:
            A list of :class:`TrustHistoryPoint` (oldest first).
        """
        points: List[TrustHistoryPoint] = []
        for h in self.trust.history(user_id):
            points.append(
                TrustHistoryPoint(
                    timestamp=datetime.fromisoformat(h["timestamp"]),
                    trust_score=h["trust_score"],
                    trigger=h.get("trigger", ""),
                    channel=h.get("channel", ""),
                )
            )
        return points

    def passport_view(self, user_id: str) -> IdentityPassportView:
        """Build the read model of an identity's Digital Identity Passport.

        Args:
            user_id: The identity to view.

        Returns:
            A populated :class:`IdentityPassportView`.
        """
        doc = self.passport.load(user_id)
        trust_score = self.trust.current(user_id)
        history = self.trust.history(user_id)
        trend = self.trust._trend(history)
        last_seen = doc.get("last_seen")
        return IdentityPassportView(
            user_id=user_id,
            masked_user_id=mask_user_id(user_id),
            trust_score=round(trust_score, 1),
            trust_band=self.trust.band(trust_score),
            trust_trend=trend,
            is_employee=bool(doc.get("is_employee", False)),
            trusted_devices=list(doc.get("trusted_devices", [])),
            trusted_locations=list(doc.get("trusted_locations", [])),
            fraud_exposure=float(doc.get("fraud_exposure", 0.0)),
            event_count=int(doc.get("event_count", 0)),
            kyc_verified=bool(doc.get("kyc_verified", False)),
            recovery_attempts=int(doc.get("recovery_attempts", 0)),
            last_seen=datetime.fromisoformat(last_seen) if last_seen else None,
            trust_history=self.trust_history(user_id),
        )

    def all_passport_views(self) -> List[IdentityPassportView]:
        """Return a passport view for every known identity.

        Returns:
            A list of :class:`IdentityPassportView`, highest-risk first.
        """
        views = [self.passport_view(p["user_id"]) for p in self.passport.all_passports()]
        views.sort(key=lambda v: v.trust_score)
        return views

    def graph_view(self) -> GraphView:
        """Build the identity-graph snapshot for fraud-ring visualisation.

        Returns:
            A populated :class:`GraphView` with nodes, edges and clusters.
        """
        g = self.risk.identity.graph
        clusters = self.risk.identity.detect_clusters(min_size=3)
        flagged_users = {u for cluster in clusters for u in cluster}

        nodes: List[GraphNode] = []
        for node_id, data in g.nodes(data=True):
            ntype = data.get("type", "unknown")
            label = node_id.split(":", 1)[1] if ":" in node_id else node_id
            risk = 0.0
            if ntype == "user":
                risk = self.risk.identity.fraud_ring_score(label)
            elif label in flagged_users:
                risk = 60.0
            nodes.append(
                GraphNode(
                    id=node_id,
                    label=mask_user_id(label) if ntype == "user" else label,
                    type=ntype,
                    risk=round(risk, 1),
                )
            )
        edges = [GraphEdge(source=u, target=v) for u, v in g.edges()]
        return GraphView(
            nodes=nodes,
            edges=edges,
            clusters=clusters,
            suspicious_clusters=len(clusters),
        )

    @staticmethod
    def _effective_risk(risk_score: float, trust_score: float, fraud_links: float) -> float:
        """Blend event risk with persistent trust into an effective risk.

        Args:
            risk_score: The raw event risk 0-100.
            trust_score: The persistent identity trust 0-100.
            fraud_links: Identity-graph fraud-ring score 0-100.

        Returns:
            The trust-adjusted effective risk 0-100.
        """
        # A trust "credit" of up to ~12 points for verified identities, and a
        # penalty of up to ~15 points for compromised ones.
        trust_adjustment = (55.0 - trust_score) * 0.22
        effective = risk_score + trust_adjustment
        # Fraud-ring links never let effective risk fall below a floor.
        if fraud_links >= 50:
            effective = max(effective, 75.0)
        return float(max(0.0, min(100.0, effective)))
