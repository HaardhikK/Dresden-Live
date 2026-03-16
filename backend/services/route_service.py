"""
Route Service — fetches and caches route geometry polylines.

Uses OSRM public routing API to build polylines between consecutive stops.
- Uses 'foot' profile for trams (tram tracks closely follow pedestrian paths in OSM)
- Uses 'driving' profile for buses
Falls back to straight-line interpolation if OSRM is unavailable.
"""
import logging
import math

import httpx

from config import OSRM_BASE_URL

logger = logging.getLogger(__name__)


class RouteService:
    """Fetches route polylines from OSRM and caches them in memory."""

    def __init__(self):
        # Cache: (from_stop_id, to_stop_id) -> [[lat, lon], ...]
        self.segment_cache: dict[tuple[str, str], list[list[float]]] = {}
        # Cache: line_id -> full polyline [[lat, lon], ...]
        self.line_polylines: dict[str, list[list[float]]] = {}
        self._client = httpx.AsyncClient(timeout=15.0)

    async def get_segment_polyline(
        self,
        from_lat: float,
        from_lon: float,
        to_lat: float,
        to_lon: float,
        from_stop_id: str = "",
        to_stop_id: str = "",
        mode: str = "Tram",
    ) -> list[list[float]]:
        """
        Get the route polyline between two points.
        Uses cache if available, otherwise queries OSRM.
        Falls back to straight line on failure.
        """
        cache_key = (from_stop_id, to_stop_id) if from_stop_id and to_stop_id else None

        # Check cache
        if cache_key and cache_key in self.segment_cache:
            return self.segment_cache[cache_key]

        # Choose OSRM profile: foot for trams (tracks ≈ pedestrian paths), driving for buses
        profile = "foot" if mode.lower() in ("tram", "straßenbahn") else "driving"

        # Try OSRM
        polyline = await self._fetch_osrm_route(from_lat, from_lon, to_lat, to_lon, profile)

        if not polyline:
            # Fallback: straight line with intermediate points for smooth rendering
            polyline = self._straight_line(from_lat, from_lon, to_lat, to_lon)

        # Cache result
        if cache_key:
            self.segment_cache[cache_key] = polyline

        return polyline

    async def _fetch_osrm_route(
        self,
        from_lat: float,
        from_lon: float,
        to_lat: float,
        to_lon: float,
        profile: str = "foot",
    ) -> list[list[float]] | None:
        """Query the public OSRM API for a route between two points."""
        try:
            # OSRM expects lon,lat order
            url = (
                f"{OSRM_BASE_URL}/route/v1/{profile}/"
                f"{from_lon},{from_lat};{to_lon},{to_lat}"
                f"?overview=full&geometries=geojson"
            )

            response = await self._client.get(url)
            if response.status_code != 200:
                logger.warning(f"OSRM returned {response.status_code} for {profile}")
                return None

            data = response.json()
            if data.get("code") != "Ok" or not data.get("routes"):
                return None

            # Extract coordinates from GeoJSON geometry
            coords = data["routes"][0]["geometry"]["coordinates"]
            # Convert from [lon, lat] to [lat, lon]
            polyline = [[c[1], c[0]] for c in coords]
            return polyline

        except Exception as e:
            logger.warning(f"OSRM request failed ({profile}): {e}")
            return None

    @staticmethod
    def _straight_line(
        from_lat: float, from_lon: float, to_lat: float, to_lon: float, num_points: int = 10
    ) -> list[list[float]]:
        """Generate intermediate points along a straight line between two coordinates."""
        points = []
        for i in range(num_points + 1):
            t = i / num_points
            lat = from_lat + t * (to_lat - from_lat)
            lon = from_lon + t * (to_lon - from_lon)
            points.append([lat, lon])
        return points

    async def close(self):
        """Clean up HTTP client."""
        await self._client.aclose()


def interpolate_along_polyline(
    polyline: list[list[float]], progress: float
) -> tuple[float, float]:
    """
    Given a polyline and a progress value (0.0 to 1.0), return the interpolated (lat, lon).

    Progress 0.0 = start of polyline, 1.0 = end of polyline.
    """
    if not polyline:
        return (0.0, 0.0)

    if progress <= 0.0:
        return (polyline[0][0], polyline[0][1])
    if progress >= 1.0:
        return (polyline[-1][0], polyline[-1][1])

    # Compute cumulative distances along the polyline
    distances = [0.0]
    for i in range(1, len(polyline)):
        d = _haversine_distance(
            polyline[i - 1][0], polyline[i - 1][1],
            polyline[i][0], polyline[i][1],
        )
        distances.append(distances[-1] + d)

    total_distance = distances[-1]
    if total_distance == 0:
        return (polyline[0][0], polyline[0][1])

    target_distance = progress * total_distance

    # Find the segment where the target distance falls
    for i in range(1, len(distances)):
        if distances[i] >= target_distance:
            # Interpolate within this segment
            segment_start = distances[i - 1]
            segment_length = distances[i] - distances[i - 1]
            if segment_length == 0:
                return (polyline[i][0], polyline[i][1])

            segment_progress = (target_distance - segment_start) / segment_length
            lat = polyline[i - 1][0] + segment_progress * (polyline[i][0] - polyline[i - 1][0])
            lon = polyline[i - 1][1] + segment_progress * (polyline[i][1] - polyline[i - 1][1])
            return (lat, lon)

    return (polyline[-1][0], polyline[-1][1])


def compute_bearing(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Compute the bearing (heading) in degrees from point 1 to point 2."""
    lat1_r = math.radians(lat1)
    lat2_r = math.radians(lat2)
    dlon_r = math.radians(lon2 - lon1)

    x = math.sin(dlon_r) * math.cos(lat2_r)
    y = math.cos(lat1_r) * math.sin(lat2_r) - math.sin(lat1_r) * math.cos(lat2_r) * math.cos(
        dlon_r
    )

    bearing = math.degrees(math.atan2(x, y))
    return (bearing + 360) % 360


def _haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Compute distance in meters between two coordinates using the Haversine formula."""
    R = 6371000  # Earth radius in meters
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)

    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    return R * c
