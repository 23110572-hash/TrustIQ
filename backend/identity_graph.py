"""Graph-based identity link analysis.

Builds a heterogeneous graph linking users, devices, IPs, phone numbers,
emails and accounts using NetworkX. Shared nodes across multiple identities
reveal fraud rings and mule-account patterns.
"""
from __future__ import annotations

import logging
from typing import Dict, List, Set

import networkx as nx

logger = logging.getLogger("trustiq.identity_graph")


class IdentityGraph:
    """Maintain and analyse the identity linkage graph."""

    def __init__(self) -> None:
        """Initialise an empty undirected identity graph."""
        self.graph = nx.Graph()

    # ------------------------------------------------------------------ #
    # Mutation
    # ------------------------------------------------------------------ #
    def _add_node(self, node_id: str, node_type: str) -> None:
        """Add a typed node to the graph if absent.

        Args:
            node_id: Unique node identifier (prefixed by type).
            node_type: One of user/device/ip/phone/email/account.
        """
        if not self.graph.has_node(node_id):
            self.graph.add_node(node_id, type=node_type)

    def add_identity(
        self,
        user_id: str,
        device_id: str | None = None,
        ip: str | None = None,
        phone: str | None = None,
        email: str | None = None,
        account: str | None = None,
    ) -> None:
        """Link a user to the identity attributes observed in an event.

        Args:
            user_id: The user identifier.
            device_id: Optional device fingerprint.
            ip: Optional IP address.
            phone: Optional phone number.
            email: Optional email address.
            account: Optional account number.
        """
        u = f"user:{user_id}"
        self._add_node(u, "user")
        for value, prefix, ntype in [
            (device_id, "device", "device"),
            (ip, "ip", "ip"),
            (phone, "phone", "phone"),
            (email, "email", "email"),
            (account, "account", "account"),
        ]:
            if value:
                node = f"{prefix}:{value}"
                self._add_node(node, ntype)
                self.graph.add_edge(u, node)

    # ------------------------------------------------------------------ #
    # Analysis
    # ------------------------------------------------------------------ #
    def shared_attribute_users(self, user_id: str) -> Dict[str, List[str]]:
        """Find other users sharing attributes with the given user.

        Args:
            user_id: The user to investigate.

        Returns:
            A mapping ``{shared_node: [other_user_ids]}``.
        """
        u = f"user:{user_id}"
        shared: Dict[str, List[str]] = {}
        if not self.graph.has_node(u):
            return shared
        for attr in self.graph.neighbors(u):
            other_users = [
                n
                for n in self.graph.neighbors(attr)
                if n.startswith("user:") and n != u
            ]
            if other_users:
                shared[attr] = [n.split(":", 1)[1] for n in other_users]
        return shared

    def fraud_ring_score(self, user_id: str) -> float:
        """Compute a fraud-ring suspicion score for a user.

        The score grows with the number of distinct other identities reachable
        through shared attributes (devices, IPs, phones, emails).

        Args:
            user_id: The user to score.

        Returns:
            A score in the range 0-100.
        """
        shared = self.shared_attribute_users(user_id)
        linked_users: Set[str] = set()
        for users in shared.values():
            linked_users.update(users)
        # Each linked identity contributes; saturate at 100.
        score = min(100.0, len(linked_users) * 25.0 + len(shared) * 10.0)
        if score:
            logger.info(
                "Fraud-ring score user=%s score=%.0f linked=%d",
                user_id,
                score,
                len(linked_users),
            )
        return float(score)

    def detect_clusters(self, min_size: int = 3) -> List[List[str]]:
        """Detect suspicious connected clusters of users.

        Args:
            min_size: Minimum number of users in a cluster to report.

        Returns:
            A list of clusters, each a list of user identifiers.
        """
        clusters: List[List[str]] = []
        for component in nx.connected_components(self.graph):
            users = [n.split(":", 1)[1] for n in component if n.startswith("user:")]
            if len(users) >= min_size:
                clusters.append(users)
        return clusters

    def shared_device_account_count(self, device_id: str) -> int:
        """Count distinct accounts opened from a single device.

        Args:
            device_id: The device fingerprint to inspect.

        Returns:
            The number of distinct user identities linked to the device.
        """
        node = f"device:{device_id}"
        if not self.graph.has_node(node):
            return 0
        return sum(1 for n in self.graph.neighbors(node) if n.startswith("user:"))
