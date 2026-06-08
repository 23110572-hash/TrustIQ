"""Beneficiary Trust Engine.

Money mostly leaves accounts through *beneficiaries*, so a beneficiary is a
first-class identity in TrustIQ. This engine scores the trustworthiness of the
payee on a transfer / beneficiary-add event and surfaces mule patterns:

* brand-new beneficiaries (added moments before a large transfer),
* unusual transfer relationships (a payee never paid before),
* mule behaviour (one beneficiary receiving from *many* unrelated senders),
* suspicious transfer networks (fan-in / fan-out via the identity graph).

It returns a beneficiary trust score (0-100, higher = safer) plus flags, and
feeds the identity graph so fan-in mule accounts light up across customers.
"""
from __future__ import annotations

import json
import logging
from typing import List, Tuple

from identity_graph import IdentityGraph
from models import BeneficiarySignal, ContextSignal

logger = logging.getLogger("trustiq.beneficiary")


class BeneficiaryTrustEngine:
    """Score beneficiaries and detect mule / fan-in networks."""

    SENDERS_KEY = "beneficiary_senders:{account}"
    KNOWN_KEY = "user_beneficiaries:{user_id}"

    def __init__(self, redis_client, identity_graph: IdentityGraph | None = None) -> None:
        """Initialise the engine.

        Args:
            redis_client: Redis-compatible client for sender/beneficiary memory.
            identity_graph: Shared identity graph for network analysis.
        """
        self.redis = redis_client
        self.identity = identity_graph or IdentityGraph()

    def _senders(self, account: str) -> List[str]:
        """Return the distinct senders previously seen for a beneficiary.

        Args:
            account: The beneficiary account.

        Returns:
            A list of sender user IDs.
        """
        raw = self.redis.get(self.SENDERS_KEY.format(account=account))
        if raw:
            try:
                return list(json.loads(raw))
            except (ValueError, TypeError):
                return []
        return []

    def _record_sender(self, account: str, user_id: str) -> int:
        """Record a sender→beneficiary relationship and return the fan-in count.

        Args:
            account: The beneficiary account.
            user_id: The sending user.

        Returns:
            The number of distinct senders to this beneficiary.
        """
        senders = self._senders(account)
        if user_id not in senders:
            senders.append(user_id)
            senders = senders[-50:]
            self.redis.setex(
                self.SENDERS_KEY.format(account=account), 86400 * 90, json.dumps(senders)
            )
        return len(senders)

    def evaluate(
        self,
        user_id: str,
        beneficiary: BeneficiarySignal,
        context: ContextSignal,
    ) -> Tuple[float, List[str], str]:
        """Score a beneficiary on a transfer / beneficiary-add event.

        Args:
            user_id: The sending customer.
            beneficiary: The beneficiary details.
            context: The event context (amount etc.).

        Returns:
            ``(beneficiary_trust_score, flags, explanation)`` where the score is
            0-100 (higher = safer).
        """
        flags: List[str] = []
        trust = 85.0

        account = beneficiary.account or "unknown_beneficiary"

        # Link into the identity graph for cross-customer fan-in analysis.
        self.identity.add_identity(user_id=user_id, account=account)
        fan_in = self._record_sender(account, user_id)

        # 1. New beneficiary.
        if beneficiary.is_new or beneficiary.prior_transfer_count == 0:
            trust -= 25.0
            flags.append("new_beneficiary")

        # 2. Just-added beneficiary used for a large transfer (classic mule).
        if beneficiary.age_days < 1 and context.amount >= 25000:
            trust -= 25.0
            flags.append("new_beneficiary_large_transfer")

        # 3. Fan-in: one payee receiving from many unrelated senders.
        if fan_in >= 5:
            trust -= 30.0
            flags.append(f"mule_fan_in_{fan_in}_senders")
        elif fan_in >= 3:
            trust -= 15.0
            flags.append(f"shared_beneficiary_{fan_in}_senders")

        # 4. Unusual relationship: no prior transfers but high value.
        if beneficiary.prior_transfer_count == 0 and context.amount >= 50000:
            trust -= 15.0
            flags.append("unusual_high_value_relationship")

        trust = float(max(0.0, min(100.0, trust)))
        explanation = (
            f"beneficiary trust {trust:.0f}: fan_in={fan_in} sender(s), "
            f"new={'yes' if 'new_beneficiary' in flags else 'no'}, "
            f"amount=₹{context.amount:,.0f}"
        )
        logger.info(
            "Beneficiary user=%s acct=%s trust=%.0f fan_in=%d flags=%s",
            user_id, account, trust, fan_in, flags,
        )
        return trust, flags, explanation
