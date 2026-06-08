"""Core ML risk-scoring engine.

Combines the behavioral, device, transaction-context (anomaly) and identity-graph
sub-scores into a single explainable 0-100 risk score with a confidence value
and a per-factor breakdown. Scores are cached in Redis for session tracking and
every decision is written to the immutable audit log.
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from typing import List

from adaptive_auth import AdaptiveAuth
from anomaly_detector import AnomalyDetector
from audit_logger import AuditLogger
from behavioral import BehavioralProcessor
from config import get_settings
from device_fingerprint import DeviceFingerprinter
from identity_graph import IdentityGraph
from models import (
    ActionType,
    BankingEvent,
    FactorContribution,
    RiskResponse,
)
from privacy_layer import hash_user_id, mask_user_id

logger = logging.getLogger("trustiq.risk_engine")

# Relative weights of the three continuous base factors (must sum to 1.0).
# The identity-graph fraud-ring signal is applied separately as an *escalator*
# because a strong ring signal should raise risk regardless of the base score.
_WEIGHTS = {
    "behavioral": 0.30,
    "device": 0.30,
    "transaction_anomaly": 0.40,
}

# Encode action types to integers for the LSTM sequence model.
_ACTION_CODE = {a: i for i, a in enumerate(ActionType)}


class RiskEngine:
    """Aggregate sub-module scores into an explainable risk decision."""

    SESSION_KEY = "risk_session:{user_id}"
    SEQUENCE_KEY = "action_seq:{user_id}"

    def __init__(self, redis_client, identity_graph: IdentityGraph | None = None) -> None:
        """Wire up all scoring sub-modules.

        Args:
            redis_client: Redis-compatible client for caching and baselines.
            identity_graph: Optional shared identity graph instance.
        """
        self.redis = redis_client
        self.settings = get_settings()
        self.behavioral = BehavioralProcessor(redis_client)
        self.device = DeviceFingerprinter(redis_client)
        self.anomaly = AnomalyDetector(
            # NOTE: the persisted ml/models/anomaly_model.pkl is trained on the
            # full 11-feature *offline* matrix (feature_engineering.to_matrix)
            # for batch evaluation. The real-time path only has the 4 context
            # signals available per event, so the runtime detector keeps its own
            # consistently-fitted 4-feature model. The trained LSTM, however,
            # shares the same action-sequence contract and is loaded here.
            model_path=None,
            lstm_path=self._model_path("lstm_model.pt"),
        )
        self.identity = identity_graph or IdentityGraph()
        self.auth = AdaptiveAuth()
        self.audit = AuditLogger()

    @staticmethod
    def _model_path(filename: str) -> str:
        """Return the conventional path to a trained model artefact.

        Args:
            filename: The model file name.

        Returns:
            An absolute path under ``ml/models`` relative to the repo root.
        """
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        return os.path.join(root, "ml", "models", filename)

    def _update_sequence(self, user_id: str, action: ActionType) -> List[int]:
        """Append the action to the user's recent sequence and return it.

        Args:
            user_id: The user performing the action.
            action: The action type just performed.

        Returns:
            The recent action sequence as a list of integer codes.
        """
        key = self.SEQUENCE_KEY.format(user_id=user_id)
        raw = self.redis.get(key)
        seq: List[int] = json.loads(raw) if raw else []
        seq.append(_ACTION_CODE[action])
        seq = seq[-20:]  # keep last 20 actions
        self.redis.setex(key, 3600, json.dumps(seq))
        return seq

    def evaluate(self, event: BankingEvent) -> RiskResponse:
        """Evaluate a banking event and return an explainable risk response.

        Args:
            event: The banking event to score.

        Returns:
            A fully-populated :class:`RiskResponse`.
        """
        response, _ = self.evaluate_detailed(event)
        return response

    def evaluate_detailed(self, event: BankingEvent):
        """Evaluate an event, returning the response *and* raw sub-scores.

        The Identity Trust Platform layers (Identity Passport, Identity Trust
        Engine, AI Analyst) need the individual behavioural / device / fraud-link
        signals. Exposing them here means the sub-modules run exactly once per
        event (no double side-effects from re-scoring).

        Args:
            event: The banking event to score.

        Returns:
            A tuple ``(RiskResponse, detail)`` where ``detail`` carries the raw
            ``behavioral_anomaly``, ``device_trust``, ``device_flags`` and
            ``fraud_links`` signals.
        """
        now = datetime.now(timezone.utc)

        # 1. Update identity graph with observed attributes.
        self.identity.add_identity(
            user_id=event.user_id,
            device_id=event.device.device_id,
            ip=event.context.ip_address,
            account=event.context.destination_account,
        )

        # 2. Sub-scores ------------------------------------------------------
        behav_anom, behav_detail = self.behavioral.score(event.user_id, event.behavioral)
        device_trust, device_flags, device_detail = self.device.score(
            event.user_id, event.device
        )
        anom_prob, anom_top = self.anomaly.detect(event)
        seq = self._update_sequence(event.user_id, event.action)
        seq_anom = self.anomaly.sequence_anomaly(seq)
        ring_score = self.identity.fraud_ring_score(event.user_id)

        # 3. Convert sub-scores to 0-100 contributions ----------------------
        behavioral_score = behav_anom * 100.0
        device_score = (1.0 - device_trust) * 100.0
        transaction_score = max(anom_prob, seq_anom) * 100.0
        identity_score = ring_score

        # Impossible-travel compounding: a new/untrusted device appearing far
        # from the user's home location is a classic account-takeover precursor,
        # so the two weak signals reinforce each other.
        is_new_device = "new_device" in device_flags
        if is_new_device and event.context.distance_from_home_km > 300:
            travel_boost = min(event.context.distance_from_home_km / 1500.0, 1.0) * 40.0
            transaction_score = min(100.0, transaction_score + travel_boost)

        factors = [
            FactorContribution(
                name="behavioral",
                score=round(behavioral_score, 2),
                weight=_WEIGHTS["behavioral"],
                detail=behav_detail,
            ),
            FactorContribution(
                name="device",
                score=round(device_score, 2),
                weight=_WEIGHTS["device"],
                detail=device_detail,
            ),
            FactorContribution(
                name="transaction_anomaly",
                score=round(transaction_score, 2),
                weight=_WEIGHTS["transaction_anomaly"],
                detail=f"point={anom_prob:.2f}, sequence={seq_anom:.2f}, "
                f"top={anom_top[0]['feature']}",
            ),
            FactorContribution(
                name="identity_graph",
                score=round(identity_score, 2),
                weight=0.0,
                detail=f"fraud_ring_links={ring_score:.0f} (escalator)",
            ),
        ]

        # 4. Risk fusion ----------------------------------------------------
        # Two complementary views are blended:
        #  * weighted average  - stable, reflects each factor's importance;
        #  * noisy-OR          - lets multiple independent risk signals
        #                        compound (corroborating evidence raises risk).
        base_factors = [f for f in factors if f.name != "identity_graph"]
        weighted = sum(f.score * f.weight for f in base_factors)

        noisy_or = 1.0
        for f in base_factors:
            noisy_or *= 1.0 - min(max(f.score, 0.0), 100.0) / 100.0
        noisy_or_score = (1.0 - noisy_or) * 100.0

        fused = 0.45 * weighted + 0.55 * noisy_or_score

        # Identity-graph escalator: a strong fraud-ring signal lifts the score
        # toward critical without dominating low-signal everyday events.
        escalated = fused + (identity_score / 100.0) * (100.0 - fused) * 0.6
        risk_score = float(max(0.0, min(100.0, escalated)))

        # 5. Confidence: agreement among the three base factors -------------
        spread = max(f.score for f in base_factors) - min(
            f.score for f in base_factors
        )
        confidence = float(round(1.0 - (spread / 200.0), 2))

        # 6. Decision -------------------------------------------------------
        band = self.auth.band(risk_score)
        response_action, message = self.auth.decide(risk_score)

        explanation = self._build_explanation(factors, message)

        # 7. Cache in Redis for session tracking ----------------------------
        self.redis.setex(
            self.SESSION_KEY.format(user_id=event.user_id),
            self.settings.redis_ttl_seconds,
            json.dumps({"score": risk_score, "band": band.value, "ts": now.isoformat()}),
        )

        # 8. Immutable audit ------------------------------------------------
        self.audit.record(
            user_id=mask_user_id(event.user_id),
            action=event.action.value,
            risk_score=risk_score,
            contributing_factors={f.name: f.score for f in factors},
            response_taken=response_action.value,
            model_version=self.settings.model_version,
        )

        logger.info(
            "RISK user=%s action=%s score=%.1f band=%s response=%s",
            hash_user_id(event.user_id),
            event.action.value,
            risk_score,
            band.value,
            response_action.value,
        )

        return RiskResponse(
            user_id=event.user_id,
            action=event.action,
            risk_score=round(risk_score, 2),
            risk_band=band,
            confidence=confidence,
            response_action=response_action,
            factors=factors,
            explanation=explanation,
            model_version=self.settings.model_version,
            timestamp=now,
        ), {
            "behavioral_anomaly": float(behav_anom),
            "device_trust": float(device_trust),
            "device_flags": list(device_flags),
            "fraud_links": float(ring_score),
            "anomaly_prob": float(anom_prob),
            "sequence_anomaly": float(seq_anom),
        }

    @staticmethod
    def _build_explanation(factors: List[FactorContribution], message: str) -> str:
        """Compose a human-readable explanation of the decision.

        Args:
            factors: The contributing factors.
            message: The adaptive-auth message.

        Returns:
            A single explanatory sentence.
        """
        top = max(factors, key=lambda f: f.score * f.weight)
        return (
            f"{message} Primary driver: {top.name} "
            f"(score {top.score:.0f}, {top.detail})."
        )
