"""Business lookup behind a provider interface.

Android cannot reliably name a business from a coordinate: ``Geocoder`` returns an
address, and the Geofencing API only works for places already registered. So a
detected fix is resolved here, once, through a swappable provider.

Current implementations:

``osm``
    Overpass API over OpenStreetMap data. Free, no account, no key. Data is ODbL:
    attribution is shown in the app's Shopping Intelligence screen and in
    ``docs/location-aware-shopping-check.md``. One request per detection.
``none``
    Disabled. The detection is still recorded, named "Unrecognised location", and
    never announced. This is the correct setting for an owner who does not want a
    coordinate leaving the server.

Provider outages degrade to ``none`` behaviour: an unresolved place is never
guessed from a nearby business.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PlaceCandidate:
    name: str
    category: str | None
    address: str | None
    distance_m: int
    confidence: float
    source: str


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> int:
    radius = 6_371_000
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lon2 - lon1)
    a = (
        math.sin(d_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    )
    return int(round(2 * radius * math.asin(math.sqrt(a))))


class PlacesProvider:
    name = "none"

    def lookup(self, latitude: float, longitude: float, radius_m: int = 120) -> list[PlaceCandidate]:
        raise NotImplementedError


class NullPlacesProvider(PlacesProvider):
    name = "none"

    def lookup(self, latitude: float, longitude: float, radius_m: int = 120) -> list[PlaceCandidate]:
        return []


class OsmPlacesProvider(PlacesProvider):
    """Nearest named shops/amenities from OpenStreetMap via Overpass."""

    name = "osm"

    # Only retail-ish tags: a detected stop next to a bus stop or a post box is not
    # a shopping visit, and the caller's confidence gate is not a substitute for
    # asking the right question.
    _QUERY = """
[out:json][timeout:{timeout}];
(
  node(around:{radius},{lat},{lon})["shop"]["name"];
  way(around:{radius},{lat},{lon})["shop"]["name"];
  node(around:{radius},{lat},{lon})["amenity"~"^(restaurant|cafe|fast_food|bar|pub|fuel|pharmacy|bank)$"]["name"];
  way(around:{radius},{lat},{lon})["amenity"~"^(restaurant|cafe|fast_food|bar|pub|fuel|pharmacy|bank)$"]["name"];
);
out center 12;
"""

    def lookup(self, latitude: float, longitude: float, radius_m: int = 120) -> list[PlaceCandidate]:
        query = self._QUERY.format(
            timeout=max(1, int(settings.places_timeout_seconds)),
            radius=max(30, min(radius_m, 400)),
            lat=round(latitude, 6),
            lon=round(longitude, 6),
        )
        try:
            response = httpx.post(
                settings.places_endpoint,
                data={"data": query},
                timeout=settings.places_timeout_seconds,
                headers={"User-Agent": "PersonalFinanceCompanion/1.0 (self-hosted)"},
            )
            response.raise_for_status()
            payload = response.json()
        except Exception as err:  # network, timeout, bad JSON: all mean "no answer"
            logger.info("places lookup failed: %s", type(err).__name__)
            return []

        candidates: list[PlaceCandidate] = []
        for element in payload.get("elements", []):
            tags = element.get("tags") or {}
            name = tags.get("name")
            if not name:
                continue
            center = element.get("center") or {}
            lat = element.get("lat", center.get("lat"))
            lon = element.get("lon", center.get("lon"))
            if lat is None or lon is None:
                continue
            distance = haversine_m(latitude, longitude, float(lat), float(lon))
            category = tags.get("shop") or tags.get("amenity")
            address = " ".join(
                filter(
                    None,
                    [
                        tags.get("addr:housenumber"),
                        tags.get("addr:street"),
                        tags.get("addr:city"),
                    ],
                )
            ) or None
            # Closer and more specific kinds are more likely to be where the user
            # actually stopped. Everything here is an inference, so the ceiling is
            # below 1 and the caller decides what to announce.
            proximity = max(0.0, 1.0 - (distance / max(radius_m, 1)))
            confidence = round(min(0.55 + 0.4 * proximity, 0.95), 3)
            candidates.append(
                PlaceCandidate(
                    name=name,
                    category=category,
                    address=address,
                    distance_m=distance,
                    confidence=confidence,
                    source="osm",
                )
            )
        # Ambiguous fixes (a mall with ten shops) must not pick a winner; the
        # caller sees the spread and asks the user instead.
        candidates.sort(key=lambda c: (c.distance_m, -c.confidence))
        return candidates[:6]


def get_provider() -> PlacesProvider:
    if settings.places_provider == "osm":
        return OsmPlacesProvider()
    return NullPlacesProvider()


def resolve_place(
    latitude: float, longitude: float, radius_m: int = 120
) -> tuple[PlaceCandidate | None, list[PlaceCandidate], bool]:
    """Return ``(best, all_candidates, is_ambiguous)`` for a coordinate."""
    candidates = get_provider().lookup(latitude, longitude, radius_m)
    if not candidates:
        return None, [], False
    best = candidates[0]
    ambiguous = False
    if len(candidates) > 1:
        runner_up = candidates[1]
        # Two businesses within ~25 m of each other, or a near-tie on distance, is
        # the shopping-centre case. Refuse to choose.
        ambiguous = (
            abs(best.distance_m - runner_up.distance_m) <= 15
            and best.name != runner_up.name
        )
    return best, candidates, ambiguous
