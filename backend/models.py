"""Pydantic data models for the TrustIQ API.

These models define the request/response contracts for every endpoint and are
shared across the risk engine, KYC guard, recovery and insider-threat modules.
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


# --------------------------------------------------------------------------- #
# Enums
# --------------------------------------------------------------------------- #
class ActionType(str, Enum):
    """Supported banking event types."""

    LOGIN = "login"
    TRANSFER = "transfer"
    OTP = "otp"
    PROFILE_CHANGE = "profile_change"
    ACCOUNT_RECOVERY = "account_recovery"


class ResponseAction(str, Enum):
    """Adaptive authentication responses, ordered by friction."""

    SILENT_PASS = "silent_pass"
    PUSH_NOTIFICATION = "push_notification"
    STEP_UP_OTP = "step_up_otp"
    BLOCK = "block"


class RiskBand(str, Enum):
    """Human-friendly risk severity bands."""

    SAFE = "safe"
    ELEVATED = "elevated"
    HIGH = "high"
    CRITICAL = "critical"


class KYCRecommendation(str, Enum):
    """Possible outcomes of a KYC onboarding evaluation."""

    APPROVE = "approve"
    REVIEW = "review"
    REJECT = "reject"


class RecoveryTier(str, Enum):
    """Verification tier required for an account-recovery attempt."""

    AUTO_APPROVE = "auto_approve"
    EMAIL_VERIFY = "email_verify"
    BIOMETRIC_VERIFY = "biometric_verify"
    IN_PERSON = "in_person"
    BLOCKED = "blocked"


# --------------------------------------------------------------------------- #
# Sub-payloads
# --------------------------------------------------------------------------- #
class BehavioralSignal(BaseModel):
    """Raw behavioral biometric signals captured on the client."""

    dwell_times: List[float] = Field(default_factory=list, description="Key dwell ms")
    flight_times: List[float] = Field(default_factory=list, description="Key flight ms")
    swipe_velocity: float = Field(0.0, description="Average swipe velocity px/ms")
    mouse_entropy: float = Field(0.0, description="Mouse movement entropy 0-1")
    tap_pressure: float = Field(0.0, description="Average tap pressure 0-1")


class DeviceSignal(BaseModel):
    """Device fingerprint attributes captured on the client."""

    device_id: str = "unknown"
    os: str = "unknown"
    browser: str = "unknown"
    screen_resolution: str = "0x0"
    timezone: str = "UTC"
    installed_fonts: List[str] = Field(default_factory=list)
    webgl_hash: str = "unknown"
    is_emulator: bool = False
    is_vpn_or_tor: bool = False


class ContextSignal(BaseModel):
    """Contextual signals about the event."""

    amount: float = 0.0
    destination_account: Optional[str] = None
    ip_address: str = "0.0.0.0"
    city: str = "unknown"
    country: str = "unknown"
    hour_of_day: int = Field(12, ge=0, le=23)
    velocity_last_hour: int = 0
    distance_from_home_km: float = 0.0


# --------------------------------------------------------------------------- #
# Event request / response
# --------------------------------------------------------------------------- #
class BankingEvent(BaseModel):
    """A single banking event submitted for risk evaluation."""

    user_id: str
    action: ActionType
    behavioral: BehavioralSignal = Field(default_factory=BehavioralSignal)
    device: DeviceSignal = Field(default_factory=DeviceSignal)
    context: ContextSignal = Field(default_factory=ContextSignal)
    timestamp: Optional[datetime] = None


class FactorContribution(BaseModel):
    """A single contributing factor to the overall risk score."""

    name: str
    score: float = Field(..., description="0-100 contribution")
    weight: float = Field(..., description="Relative weight 0-1")
    detail: str = ""


class RiskResponse(BaseModel):
    """The explainable risk result returned to the caller."""

    user_id: str
    action: ActionType
    risk_score: float = Field(..., ge=0, le=100)
    risk_band: RiskBand
    confidence: float = Field(..., ge=0, le=1)
    response_action: ResponseAction
    factors: List[FactorContribution]
    explanation: str
    model_version: str
    timestamp: datetime


# --------------------------------------------------------------------------- #
# KYC
# --------------------------------------------------------------------------- #
class KYCSubmission(BaseModel):
    """KYC onboarding data submitted for fraud screening."""

    applicant_id: str
    full_name: str
    dob: str
    address: str
    document_type: str = "aadhaar"
    document_metadata: Dict[str, Any] = Field(default_factory=dict)
    liveness_passed: bool = True
    device: DeviceSignal = Field(default_factory=DeviceSignal)
    ip_address: str = "0.0.0.0"


class KYCResult(BaseModel):
    """KYC screening outcome."""

    applicant_id: str
    kyc_risk_score: float = Field(..., ge=0, le=100)
    recommendation: KYCRecommendation
    risk_flags: List[str]
    document_score: float
    liveness_passed: bool
    velocity_flag: bool
    synthetic_identity_flag: bool
    explanation: str
    timestamp: datetime


# --------------------------------------------------------------------------- #
# Account recovery
# --------------------------------------------------------------------------- #
class RecoveryAttempt(BaseModel):
    """An account-recovery attempt submitted for evaluation."""

    user_id: str
    recovery_channel: str = Field("sms", description="sms|email|biometric|in_person")
    liveness_passed: bool = True
    behavioral: BehavioralSignal = Field(default_factory=BehavioralSignal)
    device: DeviceSignal = Field(default_factory=DeviceSignal)
    context: ContextSignal = Field(default_factory=ContextSignal)
    hours_since_last_login: float = 1.0


class RecoveryResult(BaseModel):
    """Account-recovery evaluation outcome."""

    user_id: str
    recovery_risk_score: float = Field(..., ge=0, le=100)
    recommended_tier: RecoveryTier
    risk_flags: List[str]
    explanation: str
    timestamp: datetime


# --------------------------------------------------------------------------- #
# Insider threat
# --------------------------------------------------------------------------- #
class InsiderEvent(BaseModel):
    """An employee action submitted for UEBA evaluation."""

    employee_id: str
    role: str = "teller"
    action_type: str = "record_access"
    records_accessed: int = 0
    duration_seconds: float = 60.0
    accessed_accounts: List[str] = Field(default_factory=list)
    out_of_portfolio: bool = False
    vip_access: bool = False
    data_export_mb: float = 0.0
    hour_of_day: int = Field(12, ge=0, le=23)


class InsiderAlert(BaseModel):
    """UEBA alert produced for an employee action."""

    employee_id: str
    role: str
    anomaly_type: str
    records_accessed: int
    risk_score: float = Field(..., ge=0, le=100)
    risk_level: RiskBand
    explanation: str
    timestamp: datetime


# --------------------------------------------------------------------------- #
# Dashboard / audit
# --------------------------------------------------------------------------- #
class AlertItem(BaseModel):
    """A compact anomaly alert for the live feed.

    The optional business fields make the alert directly presentable on a
    banking-operations dashboard (customer name, plain-English reason and the
    recommended action) without exposing raw model internals.
    """

    alert_id: str
    masked_user_id: str
    category: str
    event_type: str
    risk_score: float
    response_taken: str
    timestamp: datetime
    # Business-friendly enrichments (None for legacy alerts).
    customer: Optional[str] = None
    severity: Optional[str] = None
    reason: Optional[str] = None
    recommended_action: Optional[str] = None
    trust_score: Optional[float] = None
    identity_match: Optional[float] = None
    channel: Optional[str] = None
    trust_band: Optional[str] = None
    trust_trend: Optional[str] = None


class TimelinePoint(BaseModel):
    """A single point on a user's risk timeline."""

    sequence: int
    action: str
    risk_score: float
    response_taken: str
    device: str
    city: str
    timestamp: datetime


class AuditRecord(BaseModel):
    """An immutable audit-trail record."""

    id: int
    timestamp: datetime
    user_id: str
    action: str
    risk_score: float
    contributing_factors: str
    response_taken: str
    model_version: str


class DashboardStats(BaseModel):
    """Summary statistics for the dashboard header."""

    total_events: int
    active_sessions: int
    total_alerts: int
    critical_alerts: int
    average_risk_score: float
    timestamp: datetime


# =========================================================================== #
# CONTINUOUS IDENTITY TRUST PLATFORM — unified trust layer models
#
# The models below power the unified `/api/trust/evaluate` endpoint and the
# Identity Trust Engine, Identity Passport, Beneficiary Trust Engine and the
# explainable AI Fraud Analyst. They are additive: every legacy model above
# remains valid so existing channels keep working unchanged.
# =========================================================================== #
class Channel(str, Enum):
    """Banking channels the trust layer protects."""

    MOBILE_BANKING = "mobile_banking"      # bob World app
    INTERNET_BANKING = "internet_banking"  # net banking
    UPI = "upi"                            # UPI / payments
    BRANCH = "branch"                      # branch / CBS teller
    EMPLOYEE_PORTAL = "employee_portal"    # internal staff tools
    CALL_CENTER = "call_center"            # phone banking
    ATM = "atm"                            # ATM / card present


class TrustEventType(str, Enum):
    """Full event taxonomy understood by the unified trust endpoint.

    These map down to the core :class:`ActionType` for ML risk scoring so the
    Isolation Forest / LSTM contracts remain stable, while letting channels
    speak a richer business vocabulary.
    """

    LOGIN = "login"
    TRANSFER = "transfer"
    OTP = "otp"
    PROFILE_CHANGE = "profile_change"
    ACCOUNT_RECOVERY = "account_recovery"
    BENEFICIARY_ADD = "beneficiary_add"
    DEVICE_CHANGE = "device_change"
    SETTINGS_CHANGE = "settings_change"
    KYC_ONBOARDING = "kyc_onboarding"
    EMPLOYEE_ACCESS = "employee_access"
    NAVIGATION = "navigation"


# Map the rich taxonomy onto the 5 core ML action codes.
TRUST_EVENT_TO_ACTION = {
    TrustEventType.LOGIN: ActionType.LOGIN,
    TrustEventType.TRANSFER: ActionType.TRANSFER,
    TrustEventType.OTP: ActionType.OTP,
    TrustEventType.PROFILE_CHANGE: ActionType.PROFILE_CHANGE,
    TrustEventType.ACCOUNT_RECOVERY: ActionType.ACCOUNT_RECOVERY,
    TrustEventType.BENEFICIARY_ADD: ActionType.TRANSFER,
    TrustEventType.DEVICE_CHANGE: ActionType.PROFILE_CHANGE,
    TrustEventType.SETTINGS_CHANGE: ActionType.PROFILE_CHANGE,
    TrustEventType.KYC_ONBOARDING: ActionType.LOGIN,
    TrustEventType.EMPLOYEE_ACCESS: ActionType.LOGIN,
    TrustEventType.NAVIGATION: ActionType.LOGIN,
}


class TrustBand(str, Enum):
    """Persistent identity-trust severity bands (higher trust = safer)."""

    VERIFIED = "verified"        # 80-100 — strongly trusted identity
    ESTABLISHED = "established"  # 60-79  — known, consistent identity
    GUARDED = "guarded"          # 40-59  — some inconsistency, watch
    UNTRUSTED = "untrusted"      # 20-39  — significant divergence
    COMPROMISED = "compromised"  # 0-19   — likely takeover / fraud


class BeneficiarySignal(BaseModel):
    """Beneficiary details for a transfer / beneficiary-add event."""

    account: str = ""
    ifsc: str = ""
    name: str = ""
    is_new: bool = False
    age_days: float = 0.0
    prior_transfer_count: int = 0


class TrustFactor(BaseModel):
    """A single contributing factor to a trust / identity decision."""

    name: str
    score: float = Field(..., description="0-100 contribution")
    weight: float = Field(0.0, description="Relative weight 0-1")
    direction: str = Field("neutral", description="raises|lowers|neutral")
    detail: str = ""


class AIInsight(BaseModel):
    """Output of the explainable AI Fraud Analyst — never a black box."""

    headline: str
    narrative: str
    contributing_factors: List[str]
    investigation_summary: str
    recommended_action: str
    confidence: float = Field(..., ge=0, le=1)


class IdentityMatch(BaseModel):
    """How well the current event matches the customer's Identity Passport."""

    identity_match_score: float = Field(..., ge=0, le=100)
    device_match: bool
    location_match: bool
    behavioral_match: float = Field(..., ge=0, le=1)
    time_pattern_match: bool
    detail: str = ""


class TrustEvaluation(BaseModel):
    """The unified response of `POST /api/trust/evaluate`.

    A single, explainable verdict fusing persistent identity trust, identity
    match, real-time risk and an AI analyst narrative — usable by every channel.
    """

    request_id: str
    user_id: str
    channel: Channel
    event_type: TrustEventType

    trust_score: float = Field(..., ge=0, le=100, description="Persistent identity trust")
    trust_band: TrustBand
    trust_trend: str = Field("stable", description="rising|falling|stable")
    identity_match_score: float = Field(..., ge=0, le=100)

    risk_score: float = Field(..., ge=0, le=100)
    risk_band: RiskBand
    confidence: float = Field(..., ge=0, le=1)

    session_trust: float = Field(..., ge=0, le=100)
    beneficiary_trust: Optional[float] = Field(None, ge=0, le=100)

    action: ResponseAction
    explanation: str
    factors: List[TrustFactor]
    ai_insight: AIInsight
    model_version: str
    timestamp: datetime


class TrustEvaluationRequest(BaseModel):
    """Input contract for the unified `POST /api/trust/evaluate` endpoint."""

    user_id: str
    channel: Channel = Channel.MOBILE_BANKING
    event_type: TrustEventType = TrustEventType.LOGIN
    behavioral: BehavioralSignal = Field(default_factory=BehavioralSignal)
    device: DeviceSignal = Field(default_factory=DeviceSignal)
    context: ContextSignal = Field(default_factory=ContextSignal)
    beneficiary: Optional[BeneficiarySignal] = None
    session_id: Optional[str] = None
    is_employee: bool = False


class TrustHistoryPoint(BaseModel):
    """A single point in an identity's trust history."""

    timestamp: datetime
    trust_score: float
    trigger: str
    channel: str = ""


class IdentityPassportView(BaseModel):
    """Read model of a customer / employee Identity Passport."""

    user_id: str
    masked_user_id: str
    trust_score: float
    trust_band: TrustBand
    trust_trend: str
    is_employee: bool
    trusted_devices: List[str]
    trusted_locations: List[str]
    fraud_exposure: float
    event_count: int
    kyc_verified: bool
    recovery_attempts: int
    last_seen: Optional[datetime]
    trust_history: List[TrustHistoryPoint]


class GraphNode(BaseModel):
    """A node in the identity-graph visualisation."""

    id: str
    label: str
    type: str
    risk: float = 0.0


class GraphEdge(BaseModel):
    """An edge in the identity-graph visualisation."""

    source: str
    target: str


class GraphView(BaseModel):
    """Identity-graph snapshot for the dashboard visualisation."""

    nodes: List[GraphNode]
    edges: List[GraphEdge]
    clusters: List[List[str]]
    suspicious_clusters: int


class ComplianceReport(BaseModel):
    """RBI / DPDP compliance posture summary."""

    rbi_audit_ready: bool
    dpdp_compliant: bool
    total_decisions: int
    explainable_decisions: int
    pii_protected: bool
    differential_privacy: bool
    data_retention_days: int
    consent_tracked: bool
    immutable_audit: bool
    model_version: str
    controls: List[Dict[str, Any]]
    generated_at: datetime


# =========================================================================== #
# IMPOSSIBLE TRAVEL DETECTION
# =========================================================================== #
class ImpossibleTravelResult(BaseModel):
    """Outcome of geo-velocity ("impossible travel") analysis for an event."""

    impossible: bool = False
    from_city: str = ""
    to_city: str = ""
    distance_km: float = 0.0
    hours_elapsed: float = 0.0
    required_speed_kmph: float = 0.0
    risk_boost: float = 0.0
    detail: str = ""


# =========================================================================== #
# DEEPFAKE-RESISTANT RECOVERY — dynamic liveness challenge workflow
# =========================================================================== #
class LivenessChallengeRequest(BaseModel):
    """Request to begin a dynamic liveness-challenge recovery workflow."""

    user_id: str
    recovery_channel: str = "biometric"


class LivenessStep(BaseModel):
    """A single randomised liveness action the user must perform."""

    step_id: str
    instruction: str
    kind: str            # head_turn | blink | smile | read_digits | nod
    expected: str = ""   # expected response (e.g. spoken digits)


class LivenessChallenge(BaseModel):
    """A dynamic, randomised liveness challenge issued for recovery."""

    challenge_id: str
    user_id: str
    steps: List[LivenessStep]
    nonce: str
    issued_at: datetime
    expires_in_seconds: int = 90


class LivenessStepResponse(BaseModel):
    """A user's response to one liveness step."""

    step_id: str
    response: str = ""
    response_ms: float = 0.0   # time taken to perform the action
    passive_depth_ok: bool = True
    passive_texture_ok: bool = True


class LivenessVerifyRequest(BaseModel):
    """Submission of all liveness-step responses for scoring."""

    challenge_id: str
    user_id: str
    nonce: str
    responses: List[LivenessStepResponse] = Field(default_factory=list)
    device: DeviceSignal = Field(default_factory=DeviceSignal)
    context: ContextSignal = Field(default_factory=ContextSignal)


class LivenessVerifyResult(BaseModel):
    """Scored result of a dynamic liveness challenge."""

    challenge_id: str
    user_id: str
    passed: bool
    challenge_response_score: float = Field(..., ge=0, le=100)
    recovery_confidence: float = Field(..., ge=0, le=100)
    deepfake_indicators: List[str]
    recommended_tier: RecoveryTier
    explanation: str
    timestamp: datetime


# =========================================================================== #
# MULTI-CHANNEL TRUST
# =========================================================================== #
class ChannelTrust(BaseModel):
    """Per-channel trust signal snapshot."""

    channel: Channel
    events: int
    avg_risk: float
    avg_trust: float
    last_trust: float
    last_action: str
    last_seen: Optional[datetime]


class ChannelTrustView(BaseModel):
    """All channels' trust signals for the multi-channel widget."""

    channels: List[ChannelTrust]
    generated_at: datetime


# =========================================================================== #
# COMPLIANCE — consent records
# =========================================================================== #
class ConsentRecord(BaseModel):
    """A DPDP consent record for an identity."""

    user_id: str
    masked_user_id: str
    purpose: str
    granted: bool
    granted_at: datetime
    expires_at: Optional[datetime] = None
