"""Shared application state: Redis client, alert feed, timeline buffers.

Provides a single place to construct the (possibly mocked) Redis client and the
in-memory ring buffers that back the dashboard feeds, so every module shares one
consistent view of runtime state.
"""
from __future__ import annotations

import fnmatch
import logging
from collections import defaultdict, deque
from typing import Deque, Dict, List

from config import get_settings

logger = logging.getLogger("trustiq.state")


class MockRedis:
    """Minimal in-memory Redis stand-in for demo / offline mode."""

    def __init__(self) -> None:
        """Initialise the in-memory store."""
        self._store: Dict[str, str] = {}

    def get(self, key: str):
        """Return the value for a key or None."""
        return self._store.get(key)

    def set(self, key: str, value: str):
        """Set a key without expiry."""
        self._store[key] = value
        return True

    def setex(self, key: str, ttl: int, value: str):
        """Set a key with a (ignored) TTL."""
        self._store[key] = value
        return True

    def keys(self, pattern: str = "*") -> List[str]:
        """Return keys matching a glob pattern."""
        return [k for k in self._store if fnmatch.fnmatch(k, pattern)]

    def ping(self) -> bool:
        """Always succeed for the mock."""
        return True


def build_redis():
    """Construct a real Redis client, falling back to :class:`MockRedis`.

    Returns:
        A Redis-compatible client instance.
    """
    settings = get_settings()
    try:
        import redis as _redis

        client = _redis.Redis(
            host=settings.redis_host,
            port=settings.redis_port,
            db=settings.redis_db,
            decode_responses=True,
        )
        client.ping()
        logger.info("Connected to Redis at %s:%s", settings.redis_host, settings.redis_port)
        return client
    except Exception as exc:  # pragma: no cover - demo fallback
        logger.warning("Redis unavailable (%s); using in-memory MockRedis.", exc)
        return MockRedis()


class FeedStore:
    """In-memory ring buffers backing the dashboard live feeds."""

    def __init__(self, maxlen: int = 200) -> None:
        """Initialise the feed buffers.

        Args:
            maxlen: Maximum items retained per buffer.
        """
        self.alerts: Deque[dict] = deque(maxlen=maxlen)
        self.insider_alerts: Deque[dict] = deque(maxlen=maxlen)
        self.timelines: Dict[str, Deque[dict]] = defaultdict(lambda: deque(maxlen=30))
        self.event_count = 0

    def push_alert(self, alert: dict) -> None:
        """Append an anomaly alert to the live feed."""
        self.alerts.appendleft(alert)

    def push_insider(self, alert: dict) -> None:
        """Append an insider alert to the insider feed."""
        self.insider_alerts.appendleft(alert)

    def push_timeline(self, user_id: str, point: dict) -> None:
        """Append a point to a user's risk timeline."""
        self.timelines[user_id].append(point)


# Module-level singletons shared across the app.
redis_client = build_redis()
feed_store = FeedStore()
