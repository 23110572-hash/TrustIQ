"""TrustIQ FastAPI application entry point.

Wires together every module and exposes the public REST + WebSocket API:

* POST /api/event              - score a banking event
* POST /api/recovery/evaluate  - score an account-recovery attempt
* GET  /api/alerts             - recent anomaly alerts
* GET  /api/user/{id}/timeline - per-user risk timeline
* GET  /api/audit/log          - paginated audit-trail export
* GET  /api/dashboard/stats    - dashboard header summary
* WS   /ws/alerts              - live alert stream for the dashboard
"""
from __future__ import annotations

import asyncio
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import List

from fastapi import (
    Depends,
    FastAPI,
    HTTPException,
    Query,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.middleware.cors import CORSMiddleware

from account_recovery import AccountRecoveryGuard
from auth import create_access_token, verify_api_key, verify_token
from channel_trust import ChannelTrustTracker  # noqa: F401  (used via orchestrator)
from compliance import ComplianceCenter
from config import get_settings
from identity_graph import IdentityGraph
from liveness_challenge import LivenessChallengeEngine
from models import (
    AlertItem,
    AuditRecord,
    BankingEvent,
    ChannelTrustView,
    ComplianceReport,
    ConsentRecord,
    DashboardStats,
    GraphView,
    IdentityPassportView,
    LivenessChallenge,
    LivenessChallengeRequest,
    LivenessVerifyRequest,
    LivenessVerifyResult,
    RecoveryAttempt,
    RecoveryResult,
    RiskResponse,
    TimelinePoint,
    TrustEvaluation,
    TrustEvaluationRequest,
    TrustHistoryPoint,
)
from privacy_layer import mask_user_id
from risk_engine import RiskEngine
from state import feed_store, redis_client
from trust_orchestrator import TrustOrchestrator

settings = get_settings()

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
)
logger = logging.getLogger("trustiq.main")

app = FastAPI(title=settings.app_name, version=settings.app_version)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Shared singletons --------------------------------------------------------- #
identity_graph = IdentityGraph()
risk_engine = RiskEngine(redis_client, identity_graph)
recovery_guard = AccountRecoveryGuard(redis_client)
compliance_center = ComplianceCenter(redis_client, risk_engine.audit)
liveness_engine = LivenessChallengeEngine(redis_client)
trust_orchestrator = TrustOrchestrator(redis_client, risk_engine, compliance=compliance_center)


# --------------------------------------------------------------------------- #
# WebSocket connection manager
# --------------------------------------------------------------------------- #
class ConnectionManager:
    """Track active WebSocket clients and broadcast alert events."""

    def __init__(self) -> None:
        """Initialise the connection registry."""
        self.active: List[WebSocket] = []

    async def connect(self, websocket: WebSocket) -> None:
        """Accept and register a new WebSocket connection."""
        await websocket.accept()
        self.active.append(websocket)

    def disconnect(self, websocket: WebSocket) -> None:
        """Remove a closed WebSocket connection."""
        if websocket in self.active:
            self.active.remove(websocket)

    async def broadcast(self, message: dict) -> None:
        """Send a JSON message to every connected client."""
        dead: List[WebSocket] = []
        for ws in self.active:
            try:
                await ws.send_json(message)
            except Exception:  # pragma: no cover
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)


manager = ConnectionManager()


def _emit_alert(category: str, response: RiskResponse) -> None:
    """Record an alert in the feed and schedule a WebSocket broadcast.

    Args:
        category: Alert category (account_takeover/identity_trust/recovery).
        response: The risk response that triggered the alert.
    """
    alert = AlertItem(
        alert_id=str(uuid.uuid4())[:8],
        masked_user_id=mask_user_id(response.user_id),
        category=category,
        event_type=response.action.value,
        risk_score=response.risk_score,
        response_taken=response.response_action.value,
        timestamp=response.timestamp,
    ).model_dump(mode="json")
    feed_store.push_alert(alert)
    try:
        asyncio.get_running_loop().create_task(manager.broadcast(alert))
    except RuntimeError:  # pragma: no cover - no loop (e.g. in tests)
        pass


def _broadcast(payload: dict) -> None:
    """Schedule a WebSocket broadcast of an arbitrary payload (best effort).

    Args:
        payload: The JSON-serialisable message to broadcast.
    """
    try:
        asyncio.get_running_loop().create_task(manager.broadcast(payload))
    except RuntimeError:  # pragma: no cover - no running loop
        pass


def _emit_trust_alert(ev: TrustEvaluation, category: str = "identity_trust") -> None:
    """Record + broadcast an alert derived from a unified trust evaluation.

    Args:
        ev: The trust evaluation to surface.
        category: The alert category to file it under.
    """
    alert = AlertItem(
        alert_id=ev.request_id,
        masked_user_id=mask_user_id(ev.user_id),
        category=category,
        event_type=ev.event_type.value,
        risk_score=ev.risk_score,
        response_taken=ev.action.value,
        timestamp=ev.timestamp,
        customer=ev.user_id,
        severity=ev.risk_band.value,
        reason=ev.ai_insight.narrative,
        recommended_action=ev.ai_insight.recommended_action,
        trust_score=ev.trust_score,
        identity_match=ev.identity_match_score,
        channel=ev.channel.value,
        trust_band=ev.trust_band.value,
        trust_trend=ev.trust_trend,
    ).model_dump(mode="json")
    feed_store.push_alert(alert)
    _broadcast(alert)


# --------------------------------------------------------------------------- #
# Health + auth
# --------------------------------------------------------------------------- #
@app.get("/")
def root() -> dict:
    """Return a simple health/status payload."""
    return {
        "service": settings.app_name,
        "version": settings.app_version,
        "status": "operational",
    }


@app.post("/api/token")
def issue_token(username: str = "analyst") -> dict:
    """Issue a demo JWT access token.

    Args:
        username: The principal to embed in the token.

    Returns:
        A dict containing the access token and type.
    """
    token = create_access_token(username)
    return {"access_token": token, "token_type": "bearer"}


# --------------------------------------------------------------------------- #
# Core endpoints
# --------------------------------------------------------------------------- #
@app.post("/api/event", response_model=RiskResponse)
def submit_event(event: BankingEvent) -> RiskResponse:
    """Score a banking event and return the adaptive-auth decision.

    Args:
        event: The banking event to evaluate.

    Returns:
        The explainable :class:`RiskResponse`.
    """
    try:
        result = risk_engine.evaluate(event)
    except Exception as exc:  # pragma: no cover
        logger.exception("Event scoring failed")
        raise HTTPException(status_code=500, detail=str(exc))

    feed_store.event_count += 1
    feed_store.push_timeline(
        event.user_id,
        TimelinePoint(
            sequence=len(feed_store.timelines[event.user_id]) + 1,
            action=event.action.value,
            risk_score=result.risk_score,
            response_taken=result.response_action.value,
            device=event.device.device_id,
            city=event.context.city,
            timestamp=result.timestamp,
        ).model_dump(mode="json"),
    )
    if result.risk_score >= settings.risk_threshold_medium:
        _emit_alert("account_takeover", result)
    return result


@app.post("/api/recovery/evaluate", response_model=RecoveryResult)
def evaluate_recovery(attempt: RecoveryAttempt) -> RecoveryResult:
    """Evaluate an account-recovery attempt.

    Args:
        attempt: The recovery attempt.

    Returns:
        The :class:`RecoveryResult` with a verification tier.
    """
    try:
        result = recovery_guard.evaluate(attempt)
    except Exception as exc:  # pragma: no cover
        logger.exception("Recovery evaluation failed")
        raise HTTPException(status_code=500, detail=str(exc))

    if result.recovery_risk_score >= settings.risk_threshold_medium:
        feed_store.push_alert(
            AlertItem(
                alert_id=str(uuid.uuid4())[:8],
                masked_user_id=mask_user_id(attempt.user_id),
                category="recovery",
                event_type="account_recovery",
                risk_score=result.recovery_risk_score,
                response_taken=result.recommended_tier.value,
                timestamp=result.timestamp,
            ).model_dump(mode="json")
        )
    return result


# --------------------------------------------------------------------------- #
# Read endpoints
# --------------------------------------------------------------------------- #
@app.get("/api/alerts", response_model=List[AlertItem])
def get_alerts(category: str | None = Query(None)) -> List[AlertItem]:
    """Return the most recent anomaly alerts, optionally filtered.

    Args:
        category: Optional category filter.

    Returns:
        Up to 50 recent alerts.
    """
    items = list(feed_store.alerts)
    if category:
        items = [a for a in items if a["category"] == category]
    return [AlertItem(**a) for a in items[:50]]


@app.get("/api/user/{user_id}/timeline", response_model=List[TimelinePoint])
def get_timeline(user_id: str) -> List[TimelinePoint]:
    """Return the risk timeline for a specific user.

    Args:
        user_id: The user whose timeline to return.

    Returns:
        The user's last 30 timeline points.
    """
    return [TimelinePoint(**p) for p in feed_store.timelines.get(user_id, [])]


@app.get("/api/audit/log", response_model=List[AuditRecord])
def get_audit_log(
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    _: str = Depends(verify_token),
) -> List[AuditRecord]:
    """Export the audit trail (paginated). Requires a valid JWT.

    Args:
        limit: Maximum number of records.
        offset: Pagination offset.
        _: Injected token subject (auth guard).

    Returns:
        A list of :class:`AuditRecord`.
    """
    return risk_engine.audit.export(limit=limit, offset=offset)


@app.get("/api/dashboard/stats", response_model=DashboardStats)
def dashboard_stats() -> DashboardStats:
    """Return summary statistics for the dashboard header.

    Returns:
        A populated :class:`DashboardStats`.
    """
    alerts = list(feed_store.alerts)
    critical = sum(1 for a in alerts if a["risk_score"] >= settings.risk_threshold_high)
    active_sessions = len(redis_client.keys("risk_session:*"))
    avg = (
        sum(a["risk_score"] for a in alerts) / len(alerts) if alerts else 0.0
    )
    return DashboardStats(
        total_events=feed_store.event_count,
        active_sessions=active_sessions,
        total_alerts=len(alerts),
        critical_alerts=critical,
        average_risk_score=round(avg, 2),
        timestamp=datetime.now(timezone.utc),
    )


# --------------------------------------------------------------------------- #
# Identity Trust Platform endpoints
# --------------------------------------------------------------------------- #
@app.post("/api/trust/evaluate", response_model=TrustEvaluation)
def trust_evaluate(
    req: TrustEvaluationRequest,
    _: str = Depends(verify_api_key),
) -> TrustEvaluation:
    """Unified, explainable trust evaluation for any channel / event.

    This is the single brain of the Identity Trust Platform: it fuses
    real-time risk, Identity Passport match, persistent identity trust,
    beneficiary trust, impossible-travel detection and an explainable
    AI-analyst verdict into one decision.

    Requires the integration ``X-API-Key`` header — channels such as the Bank
    of Baroda core simulator authenticate with the shared integration key.

    Args:
        req: The unified trust-evaluation request.
        _: API-key guard (injected).

    Returns:
        A fully-populated :class:`TrustEvaluation`.
    """
    try:
        # DPDP: ensure a consent record exists for the identity being processed.
        if not compliance_center.has_consent(req.user_id):
            compliance_center.record_consent(req.user_id)
        ev = trust_orchestrator.evaluate(req)
    except Exception as exc:  # pragma: no cover
        logger.exception("Trust evaluation failed")
        raise HTTPException(status_code=500, detail=str(exc))

    feed_store.event_count += 1
    feed_store.push_timeline(
        req.user_id,
        TimelinePoint(
            sequence=len(feed_store.timelines[req.user_id]) + 1,
            action=ev.event_type.value,
            risk_score=ev.risk_score,
            response_taken=ev.action.value,
            device=req.device.device_id,
            city=req.context.city,
            timestamp=ev.timestamp,
        ).model_dump(mode="json"),
    )

    # Dedicated impossible-travel alert when detected.
    travel = trust_orchestrator.last_travel
    if travel is not None and travel.impossible:
        _emit_trust_alert(ev, category="impossible_travel")
    elif ev.risk_score >= settings.risk_threshold_medium:
        _emit_trust_alert(ev, category="identity_trust")
    return ev


@app.get("/api/passports", response_model=List[IdentityPassportView])
def list_passports() -> List[IdentityPassportView]:
    """Return every Identity Passport (lowest trust first).

    Returns:
        A list of :class:`IdentityPassportView`.
    """
    return trust_orchestrator.all_passport_views()


@app.get("/api/passport/{user_id}", response_model=IdentityPassportView)
def get_passport(user_id: str) -> IdentityPassportView:
    """Return a single identity's Digital Identity Passport.

    Args:
        user_id: The identity to view.

    Returns:
        The :class:`IdentityPassportView`.
    """
    return trust_orchestrator.passport_view(user_id)


@app.get("/api/identity/{user_id}/trust-history", response_model=List[TrustHistoryPoint])
def trust_history(user_id: str) -> List[TrustHistoryPoint]:
    """Return an identity's persistent trust-score history (trend over time).

    Args:
        user_id: The identity to query.

    Returns:
        A list of :class:`TrustHistoryPoint`.
    """
    return trust_orchestrator.trust_history(user_id)


@app.get("/api/graph", response_model=GraphView)
def identity_graph_view() -> GraphView:
    """Return the identity-graph snapshot for fraud-ring visualisation.

    Returns:
        A populated :class:`GraphView`.
    """
    return trust_orchestrator.graph_view()


@app.get("/api/channels/trust", response_model=ChannelTrustView)
def channels_trust() -> ChannelTrustView:
    """Return per-channel trust signals for the multi-channel widget.

    Returns:
        A populated :class:`ChannelTrustView`.
    """
    return ChannelTrustView(
        channels=trust_orchestrator.channels.all_channels(),
        generated_at=datetime.now(timezone.utc),
    )


# --------------------------------------------------------------------------- #
# Deepfake-resistant recovery — dynamic liveness challenge
# --------------------------------------------------------------------------- #
@app.post("/api/recovery/challenge", response_model=LivenessChallenge)
def issue_liveness_challenge(req: LivenessChallengeRequest) -> LivenessChallenge:
    """Issue a dynamic, randomised liveness challenge for account recovery.

    Args:
        req: The challenge request.

    Returns:
        A :class:`LivenessChallenge` describing the steps to perform.
    """
    return liveness_engine.issue(req.user_id, req.recovery_channel)


@app.post("/api/recovery/challenge/verify", response_model=LivenessVerifyResult)
def verify_liveness_challenge(req: LivenessVerifyRequest) -> LivenessVerifyResult:
    """Score a completed liveness challenge and return a recovery decision.

    Args:
        req: The verification request with per-step responses.

    Returns:
        A :class:`LivenessVerifyResult` with challenge-response and confidence.
    """
    result = liveness_engine.verify(req)
    if not result.passed:
        feed_store.push_alert(
            AlertItem(
                alert_id=result.challenge_id,
                masked_user_id=mask_user_id(result.user_id),
                category="recovery",
                event_type="account_recovery",
                risk_score=round(100.0 - result.recovery_confidence, 2),
                response_taken=result.recommended_tier.value,
                timestamp=result.timestamp,
            ).model_dump(mode="json")
        )
    return result


# --------------------------------------------------------------------------- #
# Compliance Center (DPDP + RBI)
# --------------------------------------------------------------------------- #
@app.get("/api/compliance", response_model=ComplianceReport)
def compliance_report() -> ComplianceReport:
    """Return the DPDP / RBI compliance posture report.

    Returns:
        A populated :class:`ComplianceReport`.
    """
    return compliance_center.report()


@app.get("/api/compliance/consent", response_model=List[ConsentRecord])
def consent_records() -> List[ConsentRecord]:
    """Return the DPDP consent register.

    Returns:
        A list of :class:`ConsentRecord`.
    """
    return compliance_center.consent_records()


# --------------------------------------------------------------------------- #
# WebSocket
# --------------------------------------------------------------------------- #
@app.websocket("/ws/alerts")
async def ws_alerts(websocket: WebSocket) -> None:
    """Stream live alert events to a connected dashboard client.

    Args:
        websocket: The client WebSocket connection.
    """
    await manager.connect(websocket)
    try:
        # Send a snapshot of recent alerts on connect.
        await websocket.send_json({"type": "snapshot", "alerts": list(feed_store.alerts)[:20]})
        while True:
            # Keep the connection alive; clients may send pings.
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host=settings.api_host, port=settings.api_port)
