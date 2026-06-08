"""Multi-Channel Trust Engine.

A single customer touches the bank across many channels — the mobile app, net
banking, UPI, the branch / CBS teller, ATMs and the call centre. Trust is *not*
uniform across them: a session may look perfectly normal on the mobile app yet
highly suspicious when the same identity suddenly appears on the call-centre or
branch channel.

This tracker keeps a *separate* trust signal per channel (rolling averages of
trust and risk, last action and last-seen) so the Command Center can show how an
identity behaves on each channel independently, while the persistent Identity
Trust Score remains the single cross-channel source of truth.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import List

from models import Channel, ChannelTrust

logger = logging.getLogger("trustiq.channel_trust")

# Exponential-moving-average weight for the newest observation.
_ALPHA = 0.4


class ChannelTrustTracker:
    """Maintain per-channel trust signals (global, demo-friendly aggregates)."""

    KEY = "channel_trust:{channel}"

    def __init__(self, redis_client) -> None:
        """Initialise the tracker.

        Args:
            redis_client: Redis-compatible client for per-channel state.
        """
        self.redis = redis_client

    def record(
        self,
        channel: Channel,
        trust_score: float,
        risk_score: float,
        action: str,
    ) -> None:
        """Fold a new evaluation into a channel's rolling trust signal.

        Args:
            channel: The channel the event arrived on.
            trust_score: The persistent identity trust at evaluation time.
            risk_score: The effective event risk.
            action: The adaptive-auth action taken.
        """
        key = self.KEY.format(channel=channel.value)
        raw = self.redis.get(key)
        state = json.loads(raw) if raw else {
            "events": 0, "avg_risk": risk_score, "avg_trust": trust_score,
        }
        state["events"] += 1
        state["avg_risk"] = (1 - _ALPHA) * state["avg_risk"] + _ALPHA * risk_score
        state["avg_trust"] = (1 - _ALPHA) * state["avg_trust"] + _ALPHA * trust_score
        state["last_trust"] = trust_score
        state["last_action"] = action
        state["last_seen"] = datetime.now(timezone.utc).isoformat()
        self.redis.setex(key, 86400 * 30, json.dumps(state))

    def all_channels(self) -> List[ChannelTrust]:
        """Return the trust signal for every channel (seeding empty ones).

        Returns:
            A list of :class:`ChannelTrust`, one per known channel.
        """
        out: List[ChannelTrust] = []
        for channel in Channel:
            raw = self.redis.get(self.KEY.format(channel=channel.value))
            if raw:
                s = json.loads(raw)
                out.append(
                    ChannelTrust(
                        channel=channel,
                        events=int(s.get("events", 0)),
                        avg_risk=round(float(s.get("avg_risk", 0.0)), 1),
                        avg_trust=round(float(s.get("avg_trust", 55.0)), 1),
                        last_trust=round(float(s.get("last_trust", 55.0)), 1),
                        last_action=s.get("last_action", "—"),
                        last_seen=(
                            datetime.fromisoformat(s["last_seen"]) if s.get("last_seen") else None
                        ),
                    )
                )
            else:
                out.append(
                    ChannelTrust(
                        channel=channel, events=0, avg_risk=0.0, avg_trust=55.0,
                        last_trust=55.0, last_action="—", last_seen=None,
                    )
                )
        return out
