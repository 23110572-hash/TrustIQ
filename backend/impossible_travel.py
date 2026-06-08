"""Impossible Travel Detection.

A classic account-takeover tell: the *same* identity authenticates from two
locations so far apart that no real person could have travelled between them in
the elapsed time (e.g. Mumbai at 09:00, then London at 09:20).

This detector remembers each identity's last authenticated location and time,
then computes the implied travel speed for the next event. If that speed
exceeds what is physically plausible (a fast commercial flight, ~900 km/h, plus
headroom) it raises a dedicated *impossible travel* signal and a risk boost.

Locations are resolved via a small built-in coordinate table for major Indian
and international cities, with a graceful fallback to the event's
``distance_from_home_km`` when a city is unknown.
"""
from __future__ import annotations

import json
import logging
import math
from datetime import datetime, timezone
from typing import Optional, Tuple

from models import ContextSignal, ImpossibleTravelResult

logger = logging.getLogger("trustiq.impossible_travel")

# Maximum plausible point-to-point speed (km/h): a fast jet + generous headroom.
_MAX_PLAUSIBLE_KMPH = 950.0

# Approximate coordinates (lat, lon) for cities seen in demos.
_CITY_COORDS = {
    "mumbai": (19.0760, 72.8777),
    "delhi": (28.7041, 77.1025),
    "new delhi": (28.6139, 77.2090),
    "bengaluru": (12.9716, 77.5946),
    "bangalore": (12.9716, 77.5946),
    "chennai": (13.0827, 80.2707),
    "kolkata": (22.5726, 88.3639),
    "hyderabad": (17.3850, 78.4867),
    "pune": (18.5204, 73.8567),
    "ahmedabad": (23.0225, 72.5714),
    "jaipur": (26.9124, 75.7873),
    "lucknow": (26.8467, 80.9462),
    "vadodara": (22.3072, 73.1812),
    "surat": (21.1702, 72.8311),
    "london": (51.5074, -0.1278),
    "dubai": (25.2048, 55.2708),
    "singapore": (1.3521, 103.8198),
    "new york": (40.7128, -74.0060),
    "moscow": (55.7558, 37.6173),
    "lagos": (6.5244, 3.3792),
}


class ImpossibleTravelDetector:
    """Detect geographically impossible logins for an identity."""

    KEY = "geo_last_seen:{user_id}"

    def __init__(self, redis_client) -> None:
        """Initialise the detector.

        Args:
            redis_client: Redis-compatible client for last-seen geo state.
        """
        self.redis = redis_client

    @staticmethod
    def _haversine(a: Tuple[float, float], b: Tuple[float, float]) -> float:
        """Great-circle distance in km between two (lat, lon) points.

        Args:
            a: First coordinate (lat, lon).
            b: Second coordinate (lat, lon).

        Returns:
            Distance in kilometres.
        """
        r = 6371.0
        lat1, lon1, lat2, lon2 = map(math.radians, [a[0], a[1], b[0], b[1]])
        dlat = lat2 - lat1
        dlon = lon2 - lon1
        h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
        return 2 * r * math.asin(math.sqrt(h))

    def _coords(self, city: str) -> Optional[Tuple[float, float]]:
        """Resolve a city name to coordinates, if known."""
        return _CITY_COORDS.get((city or "").strip().lower())

    def evaluate(self, user_id: str, context: ContextSignal) -> ImpossibleTravelResult:
        """Evaluate the current event for impossible travel and update state.

        Args:
            user_id: The identity being evaluated.
            context: The event context (city, time).

        Returns:
            A populated :class:`ImpossibleTravelResult`.
        """
        now = datetime.now(timezone.utc)
        city = context.city or "unknown"
        coords = self._coords(city)

        raw = self.redis.get(self.KEY.format(user_id=user_id))
        prior = None
        if raw:
            try:
                prior = json.loads(raw)
            except (ValueError, TypeError):
                prior = None

        result = ImpossibleTravelResult(to_city=city)

        if prior and prior.get("city") and prior["city"].lower() != city.lower():
            last_time = datetime.fromisoformat(prior["ts"])
            hours = max((now - last_time).total_seconds() / 3600.0, 1e-4)

            # Prefer real coordinates; fall back to home-distance heuristic.
            if coords and prior.get("coords"):
                distance = self._haversine(tuple(prior["coords"]), coords)
            else:
                distance = abs(context.distance_from_home_km - prior.get("distance", 0.0))

            speed = distance / hours
            result.from_city = prior["city"]
            result.distance_km = round(distance, 1)
            result.hours_elapsed = round(hours, 3)
            result.required_speed_kmph = round(speed, 1)

            if distance > 400 and speed > _MAX_PLAUSIBLE_KMPH:
                result.impossible = True
                # Boost scales with how far beyond plausible the speed is.
                over = min(speed / _MAX_PLAUSIBLE_KMPH, 8.0)
                result.risk_boost = round(min(45.0, 18.0 + over * 4.0), 1)
                result.detail = (
                    f"{prior['city']} → {city}: {distance:.0f} km in "
                    f"{hours:.1f} h needs {speed:.0f} km/h (impossible). "
                    f"Likely account takeover."
                )
                logger.warning(
                    "IMPOSSIBLE TRAVEL user=%s %s->%s %.0fkm/%.2fh=%.0fkm/h",
                    user_id, prior["city"], city, distance, hours, speed,
                )
            else:
                result.detail = (
                    f"{prior['city']} → {city}: {distance:.0f} km in "
                    f"{hours:.1f} h is plausible ({speed:.0f} km/h)."
                )

        # Update last-seen geo state for this identity.
        self.redis.setex(
            self.KEY.format(user_id=user_id),
            86400 * 30,
            json.dumps(
                {
                    "city": city,
                    "coords": list(coords) if coords else None,
                    "distance": context.distance_from_home_km,
                    "ts": now.isoformat(),
                }
            ),
        )
        return result
