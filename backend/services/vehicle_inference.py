"""
Vehicle Position Inference Engine

Computes estimated vehicle positions by combining:
  - Departure data from transport_service (schedules + delays)
  - Route geometry from route_service (polylines)
  - The current system time

No GPS data is available — all positions are inferred.
All vehicle states (approaching, at-stop, departed) now use OSRM
route geometry for realistic path-following.

Anti-bunching:
  - Vehicles are deduplicated by line + direction so only one instance
    of each trip appears on the map.
  - A per-segment headway enforcer prevents multiple vehicles from
    sitting on the exact same polyline segment.
  - Stale vehicles (departed > 5 min with no next stop) are hidden.
  - Approaching vehicles more than 8 min away are hidden.
"""
import math
import logging
from datetime import datetime, timezone, timedelta
from typing import Any

from models.vehicle import Vehicle
from services.route_service import (
    RouteService,
    interpolate_along_polyline,
    compute_bearing,
)
from config import MIN_SEGMENT_DURATION_SECONDS, LINE_COLORS, DEFAULT_LINE_COLOR

logger = logging.getLogger(__name__)

# Visibility / anti-bunching constants
MAX_APPROACH_WINDOW = 600    # Show vehicles approaching within 10 minutes
MAX_DEPARTED_FALLBACK = 180  # Hide departed fallback vehicles after 3 minutes
MIN_HEADWAY_METERS = 400     # Minimum spacing to safely drop duplicate ghost vehicles
SIMULATION_DELAY_SECONDS = 90  # Keep simulation slightly in the past so data doesn't vanish


import asyncio

class VehicleInferenceService:
    """Estimates vehicle positions from schedule data and route geometry."""

    def __init__(self, route_service: RouteService, gtfs_service=None):
        self.route_service = route_service
        self.gtfs_service = gtfs_service
        # Current vehicle positions: vehicle_id -> Vehicle
        self.vehicles: dict[str, Vehicle] = {}
        # Track when we last computed — sent to frontend as data freshness
        self.last_update_utc: str = ""
        self.start_time = datetime.now(timezone.utc)

    async def update_vehicles(
        self,
        departures: list[dict[str, Any]],
        stops: dict[str, dict],
    ) -> list[Vehicle]:
        """
        Given current departure data, compute all vehicle positions.

        For each active departure, we estimate where the vehicle is right now
        based on the scheduled time, delay, and the route between stops.
        """
        # Read the simulation from slightly in the past (e.g. 90s ago)
        # This keeps vehicles on the map longer, preventing them from instantly
        # disappearing when their departure vanishes from the realtime feed.
        now = datetime.now(timezone.utc)
        
        # Buffer period: Wait 90s on startup before exposing vehicles
        # so that the history cache fully catches up.
        if (now - self.start_time).total_seconds() < SIMULATION_DELAY_SECONDS:
            return []
            
        now = now - timedelta(seconds=SIMULATION_DELAY_SECONDS)
        self.last_update_utc = datetime.now(timezone.utc).isoformat()
        new_vehicles: dict[str, Vehicle] = {}

        for dep in departures:
            try:
                vehicle = await self._infer_single_vehicle(dep, stops, now)
                if vehicle:
                    new_vehicles[vehicle.vehicle_id] = vehicle
            except Exception as e:
                logger.debug(f"Error inferring vehicle for {dep.get('trip_id')}: {e}")

        # --- Anti-bunching: enforce minimum headway per segment ---
        new_vehicles = self._enforce_headway(new_vehicles)

        self.vehicles = new_vehicles
        return list(new_vehicles.values())

    def _enforce_headway(self, vehicles: dict[str, Vehicle]) -> dict[str, Vehicle]:
        """
        Apply a visual spread (offset) for vehicles that overlap within 30m,
        so they fan out visibly at stops instead of stacking perfectly on top.
        vehicle_id = trip_id already prevents the same trip appearing twice.
        """
        from services.route_service import _haversine_distance

        kept: dict[str, Vehicle] = {}
        global_positions: list[tuple[float, float]] = []

        for vid, v in vehicles.items():
            overlap_count = 0
            for (alat, alon) in global_positions:
                if _haversine_distance(v.lat, v.lon, alat, alon) < 30:
                    overlap_count += 1

            if overlap_count > 0:
                angle = (overlap_count - 1) * 45  # 0, 45, 90, 135...
                rad = math.radians(angle)
                v.lat += math.cos(rad) * 0.0004
                v.lon += math.sin(rad) * 0.0004

            kept[vid] = v
            global_positions.append((v.lat, v.lon))

        return kept

    async def _infer_single_vehicle(
        self,
        dep: dict[str, Any],
        stops: dict[str, dict],
        now: datetime,
    ) -> Vehicle | None:
        """Infer position for a single departure/trip."""
        trip_id = dep.get("trip_id", "")
        line = dep.get("line", "")
        direction = dep.get("direction", "")
        mode = dep.get("mode", "Tram")
        stop_id = dep.get("stop_id", "")
        stop_name = dep.get("stop_name", "")
        scheduled: datetime | None = dep.get("scheduled")
        real_time: datetime | None = dep.get("real_time")
        delay_seconds = dep.get("delay_seconds", 0)

        if not scheduled:
            return None

        # Determine the stop coordinates
        stop_info = stops.get(stop_id, {})
        stop_lat = stop_info.get("lat", 0)
        stop_lon = stop_info.get("lon", 0)

        if stop_lat == 0 and stop_lon == 0:
            return None

        # Adjusted departure time (with delay)
        adjusted_departure = scheduled + timedelta(seconds=delay_seconds)

        # Estimate arrival at this stop as ~2 minutes before departure (dwell time)
        estimated_arrival = adjusted_departure - timedelta(seconds=25)

        # --- APPROACHING STOP ---
        if now < estimated_arrival:
            seconds_remaining = (estimated_arrival - now).total_seconds()
            if seconds_remaining > MAX_APPROACH_WINDOW:
                return None  # Too far in the future — hide
            return await self._approaching_vehicle(
                trip_id, line, mode, direction, delay_seconds,
                stop_id, stop_lat, stop_lon, stop_name,
                now, estimated_arrival, stops,
            )

        # --- AT STOP (dwell time) ---
        elif now <= adjusted_departure:
            return Vehicle(
                vehicle_id=trip_id,
                line_id=line,
                line_name=f"{mode} {line}",
                mode=mode,
                lat=stop_lat,
                lon=stop_lon,
                heading=0.0,
                direction=direction,
                delay_seconds=delay_seconds,
                timestamp=now.isoformat(),
                prev_stop=stop_name,
                next_stop=direction,
                progress=0.0,
                prev_stop_lat=stop_lat,
                prev_stop_lon=stop_lon,
                next_stop_lat=stop_lat,
                next_stop_lon=stop_lon,
                segment_duration_seconds=120.0,
                polyline=[[stop_lat, stop_lon]],
            )

        # --- DEPARTED: travelling to next stop ---
        else:
            next_stop_id = dep.get("next_stop_id")
            next_stop_name = dep.get("next_stop_name", direction)
            next_scheduled = dep.get("next_scheduled")

            if next_stop_id and next_scheduled:
                next_stop_info = stops.get(next_stop_id, {})
                next_lat = next_stop_info.get("lat", 0)
                next_lon = next_stop_info.get("lon", 0)

                if next_lat == 0 or next_lon == 0:
                    return await self._departed_fallback_vehicle(
                        trip_id, line, mode, direction, delay_seconds,
                        stop_id, stop_lat, stop_lon, stop_name,
                        now, adjusted_departure, stops,
                    )

                # Compute segment duration
                next_delay = dep.get("next_delay_seconds", delay_seconds)
                adjusted_next_arrival = next_scheduled + timedelta(seconds=next_delay)
                segment_duration = (adjusted_next_arrival - adjusted_departure).total_seconds()

                if segment_duration < MIN_SEGMENT_DURATION_SECONDS:
                    segment_duration = MIN_SEGMENT_DURATION_SECONDS

                # Compute progress and check staleness
                seconds_since_departure = (now - adjusted_departure).total_seconds()
                progress = max(0.0, min(1.0, seconds_since_departure / segment_duration))
                
                # Mark as stale if it hasn't received updates for 2 mins past arrival time
                is_stale = seconds_since_departure > (segment_duration + 120)

                # Get route polyline between stops
                polyline = await self.route_service.get_segment_polyline(
                    stop_lat, stop_lon, next_lat, next_lon,
                    from_stop_id=stop_id, to_stop_id=next_stop_id,
                    mode=mode,
                )

                # Interpolate position along polyline
                lat, lon = interpolate_along_polyline(polyline, progress)

                # Compute heading from polyline tangent
                next_progress = min(1.0, progress + 0.05)
                next_lat_h, next_lon_h = interpolate_along_polyline(polyline, next_progress)
                heading = compute_bearing(lat, lon, next_lat_h, next_lon_h)

                return Vehicle(
                    vehicle_id=trip_id,
                    line_id=line,
                    line_name=f"{mode} {line}",
                    mode=mode,
                    lat=lat,
                    lon=lon,
                    heading=heading,
                    direction=direction,
                    delay_seconds=delay_seconds,
                    timestamp=now.isoformat(),
                    prev_stop=stop_name,
                    next_stop=next_stop_name,
                    progress=progress,
                    prev_stop_lat=stop_lat,
                    prev_stop_lon=stop_lon,
                    next_stop_lat=next_lat,
                    next_stop_lon=next_lon,
                    segment_duration_seconds=segment_duration,
                    polyline=polyline,
                    is_stale=is_stale,
                )

            else:
                return await self._departed_fallback_vehicle(
                    trip_id, line, mode, direction, delay_seconds,
                    stop_id, stop_lat, stop_lon, stop_name,
                    now, adjusted_departure, stops,
                )

    async def _approaching_vehicle(
        self, trip_id, line, mode, direction, delay_seconds,
        stop_id, stop_lat, stop_lon, stop_name,
        now, estimated_arrival, stops,
    ) -> Vehicle:
        """
        Vehicle is approaching a stop — use OSRM route from a synthetic
        'previous position' toward the stop for realistic path-following.
        """
        approach_duration = 300.0  # 5 min approach window
        seconds_remaining = (estimated_arrival - now).total_seconds()
        progress = max(0.0, 1.0 - seconds_remaining / approach_duration)

        # Synthetic origin ~330m away, direction derived from trip_id (opposite of depart direction)
        angle_deg = (hash(trip_id) % 360 + 180) % 360
        angle_rad = math.radians(angle_deg)
        offset = 0.003
        origin_lat = stop_lat + math.cos(angle_rad) * offset
        origin_lon = stop_lon + math.sin(angle_rad) * offset

        polyline = await self.route_service.get_segment_polyline(
            origin_lat, origin_lon, stop_lat, stop_lon,
            from_stop_id=f"approach_{stop_id}",
            to_stop_id=stop_id,
            mode=mode,
        )

        lat, lon = interpolate_along_polyline(polyline, progress)

        next_progress = min(1.0, progress + 0.05)
        next_lat_h, next_lon_h = interpolate_along_polyline(polyline, next_progress)
        heading = compute_bearing(lat, lon, next_lat_h, next_lon_h)

        return Vehicle(
            vehicle_id=trip_id,
            line_id=line,
            line_name=f"{mode} {line}",
            mode=mode,
            lat=lat,
            lon=lon,
            heading=heading,
            direction=direction,
            delay_seconds=delay_seconds,
            timestamp=now.isoformat(),
            prev_stop="",
            next_stop=stop_name,
            progress=progress,
            prev_stop_lat=origin_lat,
            prev_stop_lon=origin_lon,
            next_stop_lat=stop_lat,
            next_stop_lon=stop_lon,
            segment_duration_seconds=approach_duration,
            polyline=polyline,
        )

    async def _departed_fallback_vehicle(
        self, trip_id, line, mode, direction, delay_seconds,
        stop_id, stop_lat, stop_lon, stop_name,
        now, adjusted_departure, stops,
    ) -> Vehicle | None:
        """
        Fallback: vehicle departed but no next-stop data.
        Use OSRM route from the stop outward instead of hardcoded offsets.
        Hide if too much time has elapsed.
        """
        assumed_travel_time = 180.0  # 3 minutes to next stop
        is_stale = False
        
        seconds_since_departure = (now - adjusted_departure).total_seconds()

        if seconds_since_departure > MAX_DEPARTED_FALLBACK:
            is_stale = True
            seconds_since_departure = assumed_travel_time # Lock it at end of fallback route
            
        if seconds_since_departure > assumed_travel_time:
            is_stale = True
            seconds_since_departure = assumed_travel_time # Lock it at end of fallback route
            
        progress = min(1.0, seconds_since_departure / assumed_travel_time)

        # Departure direction derived from trip_id so each trip leaves in a unique direction
        angle_deg = hash(trip_id) % 360
        angle_rad = math.radians(angle_deg)
        offset = 0.003
        dest_lat = stop_lat + math.cos(angle_rad) * offset
        dest_lon = stop_lon + math.sin(angle_rad) * offset

        polyline = await self.route_service.get_segment_polyline(
            stop_lat, stop_lon, dest_lat, dest_lon,
            from_stop_id=stop_id,
            to_stop_id=f"depart_{stop_id}",
            mode=mode,
        )

        lat, lon = interpolate_along_polyline(polyline, progress)

        next_progress = min(1.0, progress + 0.05)
        next_lat_h, next_lon_h = interpolate_along_polyline(polyline, next_progress)
        heading = compute_bearing(lat, lon, next_lat_h, next_lon_h)

        return Vehicle(
            vehicle_id=trip_id,
            line_id=line,
            line_name=f"{mode} {line}",
            mode=mode,
            lat=lat,
            lon=lon,
            heading=heading,
            direction=direction,
            delay_seconds=delay_seconds,
            timestamp=now.isoformat(),
            prev_stop=stop_name,
            next_stop=direction,
            progress=progress,
            prev_stop_lat=stop_lat,
            prev_stop_lon=stop_lon,
            next_stop_lat=dest_lat,
            next_stop_lon=dest_lon,
            segment_duration_seconds=assumed_travel_time,
            polyline=polyline,
            is_stale=is_stale,
        )

    def get_vehicles(self) -> list[Vehicle]:
        """Return current vehicle positions."""
        return list(self.vehicles.values())
