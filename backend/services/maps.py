"""OpenStreetMap context: nearby landmarks (Overpass), bus routes through nearby
stops (Overpass route relations) and the current street (Nominatim reverse).

Directions are relative to the phone's compass heading when the client sends one;
otherwise only distance and compass bearing are reported.
"""

import logging
import math
from dataclasses import dataclass, field

import httpx

from config import Settings
from schemas.request import Location
from schemas.response import BusRoute, Landmark

log = logging.getLogger(__name__)

SEARCH_RADIUS_M = 200

# OSM tag -> spoken kind. Order matters: first match wins.
_KINDS: list[tuple[str, str, str]] = [
    ("highway", "bus_stop", "bus stop"),
    ("public_transport", "platform", "bus stop"),
    ("highway", "crossing", "pedestrian crossing"),
    ("highway", "traffic_signals", "traffic signal"),
    ("railway", "station", "railway station"),
    ("station", "subway", "metro station"),
    ("amenity", "hospital", "hospital"),
    ("amenity", "pharmacy", "pharmacy"),
    ("amenity", "police", "police station"),
    ("amenity", "atm", "ATM"),
    ("amenity", "bank", "bank"),
    ("amenity", "toilets", "public toilet"),
]


@dataclass
class MapContext:
    street: str | None = None
    landmarks: list[Landmark] = field(default_factory=list)
    bus_routes: list[BusRoute] = field(default_factory=list)

    def as_prompt(self) -> str:
        lines = []
        if self.street:
            lines.append(f"User is on or near: {self.street}")
        for lm in self.landmarks[:8]:
            where = lm.direction or f"bearing {lm.bearing_deg} degrees"
            lines.append(f"- {lm.kind} '{lm.name}': {lm.distance_m} m, {where}")
        if self.bus_routes:
            routes = ", ".join(
                f"{r.ref} to {r.to}" if r.to else r.ref for r in self.bus_routes[:10]
            )
            lines.append(f"Bus routes stopping within {SEARCH_RADIUS_M} m (OSM, may be incomplete): {routes}")
        return "\n".join(lines)


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6_371_000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def bearing_deg(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dl = math.radians(lon2 - lon1)
    x = math.sin(dl) * math.cos(p2)
    y = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dl)
    return (math.degrees(math.atan2(x, y)) + 360) % 360


def relative_direction(bearing: float, heading: float) -> str:
    """Clock-free wording; clock-face directions confuse many first-time users."""
    rel = (bearing - heading + 360) % 360
    if rel < 25 or rel >= 335:
        return "straight ahead"
    if rel < 70:
        return "ahead on your right"
    if rel < 115:
        return "on your right"
    if rel < 245:
        return "behind you"
    if rel < 290:
        return "on your left"
    return "ahead on your left"


class MapsClient:
    def __init__(self, http: httpx.AsyncClient, settings: Settings):
        self._http = http
        self._s = settings

    async def context(self, loc: Location) -> MapContext:
        elements = await self._overpass(loc)
        ctx = MapContext()
        stop_ids: set[int] = set()
        for el in elements:
            if el.get("type") == "relation":
                tags = el.get("tags", {})
                if tags.get("route") == "bus" and tags.get("ref"):
                    ctx.bus_routes.append(
                        BusRoute(ref=tags["ref"], name=tags.get("name"), to=tags.get("to"))
                    )
                continue
            tags = el.get("tags", {})
            lat, lon = el.get("lat") or el.get("center", {}).get("lat"), el.get("lon") or el.get("center", {}).get("lon")
            if lat is None or lon is None:
                continue
            kind = next((k for key, val, k in _KINDS if tags.get(key) == val), None)
            if not kind:
                kind = "shop" if "shop" in tags else None
            if not kind:
                continue
            if kind == "bus stop":
                stop_ids.add(el["id"])
            b = bearing_deg(loc.lat, loc.lon, lat, lon)
            ctx.landmarks.append(
                Landmark(
                    name=tags.get("name:en") or tags.get("name") or kind,
                    kind=kind,
                    distance_m=round(haversine_m(loc.lat, loc.lon, lat, lon)),
                    bearing_deg=round(b),
                    direction=relative_direction(b, loc.heading_deg)
                    if loc.heading_deg is not None
                    else None,
                )
            )
        ctx.landmarks.sort(key=lambda lm: lm.distance_m)
        # Dedupe bus routes by ref+destination (both directions are separate relations).
        seen: set[tuple] = set()
        ctx.bus_routes = [
            r for r in ctx.bus_routes if not ((r.ref, r.to) in seen or seen.add((r.ref, r.to)))
        ]
        try:
            ctx.street = await self._reverse(loc)
        except httpx.HTTPError as e:
            log.info("nominatim failed: %s", e)
        return ctx

    async def _overpass(self, loc: Location) -> list[dict]:
        r, lat, lon = SEARCH_RADIUS_M, loc.lat, loc.lon
        query = f"""
[out:json][timeout:5];
(
  node(around:{r},{lat},{lon})[highway~"^(bus_stop|crossing|traffic_signals)$"];
  node(around:{r},{lat},{lon})[public_transport=platform];
  nwr(around:{r},{lat},{lon})[amenity~"^(hospital|pharmacy|police|atm|bank|toilets)$"];
  nwr(around:{r},{lat},{lon})[railway=station];
  nwr(around:{r},{lat},{lon})[shop][name];
)->.near;
.near out center 60;
node.near[highway=bus_stop]->.stops;
rel(bn.stops)[route=bus];
out tags;
"""
        resp = await self._http.post(
            self._s.overpass_url,
            data={"data": query},
            headers={"User-Agent": self._s.osm_user_agent},
        )
        resp.raise_for_status()
        return resp.json().get("elements", [])

    async def _reverse(self, loc: Location) -> str | None:
        resp = await self._http.get(
            self._s.nominatim_url,
            params={"lat": loc.lat, "lon": loc.lon, "format": "jsonv2", "zoom": 17},
            headers={"User-Agent": self._s.osm_user_agent},
        )
        resp.raise_for_status()
        addr = resp.json().get("address", {})
        road = addr.get("road")
        area = addr.get("suburb") or addr.get("neighbourhood")
        return ", ".join(p for p in (road, area) if p) or None
