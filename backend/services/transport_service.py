"""
Transport Service — polls DVB departures via dvbpy.

Responsibilities:
  - Query dvbpy.monitor() for each key stop on a timer
  - Track active departures and their delays
  - Provide departure data for the vehicle inference engine

Performance notes:
  - dvb.find / dvb.monitor / dvb.lines are synchronous HTTP calls.
  - We wrap them with asyncio.to_thread and run them concurrently
    via asyncio.gather so startup takes ~5s instead of ~60s.
"""
import asyncio
import json
import logging
import os
from datetime import datetime, timezone, timedelta
from typing import Any

import dvb

from config import KEY_STOPS, DEPARTURE_LIMIT

logger = logging.getLogger(__name__)

STOPS_CACHE_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "stops_cache.json")


class TransportService:
    """Polls DVB for departure data and maintains an in-memory snapshot."""

    def __init__(self):
        # {stop_id: [departure_dict, ...]}
        self.departures_by_stop: dict[str, list[dict[str, Any]]] = {}
        # {stop_id: Stop info}
        self.stops: dict[str, dict] = {}
        # {line_name: {directions, mode, stops_seen}}
        self.lines: dict[str, dict] = {}
        # Track all unique departures (trip_id -> departure info)
        self.active_trips: dict[str, dict[str, Any]] = {}
        self._running = False

    # ------------------------------------------------------------------
    # Disk cache helpers
    # ------------------------------------------------------------------
    def _load_cached_stops(self) -> bool:
        """Try loading stop metadata from disk cache."""
        try:
            if os.path.exists(STOPS_CACHE_PATH):
                with open(STOPS_CACHE_PATH, "r", encoding="utf-8") as f:
                    cached = json.load(f)
                if isinstance(cached, dict) and len(cached) > 0:
                    self.stops = cached
                    logger.info(f"Loaded {len(cached)} stops from disk cache")
                    return True
        except Exception as e:
            logger.warning(f"Could not read stops cache: {e}")
        return False

    def _save_stops_cache(self):
        """Persist stop metadata to disk."""
        try:
            with open(STOPS_CACHE_PATH, "w", encoding="utf-8") as f:
                json.dump(self.stops, f, ensure_ascii=False, indent=2)
            logger.info(f"Saved {len(self.stops)} stops to disk cache")
        except Exception as e:
            logger.warning(f"Could not write stops cache: {e}")

    # ------------------------------------------------------------------
    # Async wrappers around blocking dvbpy calls
    # ------------------------------------------------------------------
    @staticmethod
    async def _find_stop(stop_name: str):
        """Run dvb.find in a thread so it doesn't block the event loop."""
        return await asyncio.to_thread(dvb.find, stop_name)

    @staticmethod
    async def _monitor_stop(stop_name: str, limit: int):
        """Run dvb.monitor in a thread."""
        return await asyncio.to_thread(dvb.monitor, stop_name, limit=limit)

    @staticmethod
    async def _lines_at_stop(stop_id: str):
        """Run dvb.lines in a thread."""
        return await asyncio.to_thread(dvb.lines, stop_id)

    # ------------------------------------------------------------------
    # Initialisation
    # ------------------------------------------------------------------
    async def initialize(self):
        """Load initial stop and line data — fully concurrent."""
        logger.info("Initializing transport service — loading stops...")

        # 1. Try to load from cache first for instant availability
        cache_hit = self._load_cached_stops()

        # 2. Fetch fresh data in parallel (even if cache exists, refresh in bg)
        async def fetch_stop(stop_name: str, stop_id: str):
            try:
                results = await asyncio.wait_for(self._find_stop(stop_name), timeout=8)
                if results:
                    stop = results[0]
                    self.stops[stop_id] = {
                        "id": stop_id,
                        "name": stop.name,
                        "lat": stop.coords.lat if stop.coords else 0,
                        "lon": stop.coords.lng if stop.coords else 0,
                        "city": stop.city or "Dresden",
                    }
            except asyncio.TimeoutError:
                logger.warning(f"Timeout finding stop {stop_name}")
                if stop_id not in self.stops:
                    self.stops[stop_id] = {
                        "id": stop_id, "name": stop_name,
                        "lat": 0, "lon": 0, "city": "Dresden",
                    }
            except Exception as e:
                logger.warning(f"Could not find stop {stop_name}: {e}")
                if stop_id not in self.stops:
                    self.stops[stop_id] = {
                        "id": stop_id, "name": stop_name,
                        "lat": 0, "lon": 0, "city": "Dresden",
                    }

        # Run all stop lookups concurrently
        await asyncio.gather(
            *[fetch_stop(name, sid) for name, sid in KEY_STOPS],
            return_exceptions=True,
        )

        # 3. Fetch lines concurrently
        async def fetch_lines(stop_name: str, stop_id: str):
            try:
                lines_at_stop = await asyncio.wait_for(
                    self._lines_at_stop(stop_id), timeout=8
                )
                for line in lines_at_stop:
                    if line.name not in self.lines:
                        self.lines[line.name] = {
                            "id": line.name,
                            "name": f"{line.mode} {line.name}",
                            "mode": line.mode,
                            "directions": list(line.directions) if line.directions else [],
                            "stops_seen": set(),
                        }
                    self.lines[line.name]["stops_seen"].add(stop_id)
            except asyncio.TimeoutError:
                logger.warning(f"Timeout getting lines for {stop_id}")
            except Exception as e:
                logger.warning(f"Could not get lines for stop {stop_id}: {e}")

        await asyncio.gather(
            *[fetch_lines(name, sid) for name, sid in KEY_STOPS],
            return_exceptions=True,
        )

        # 4. Persist to disk if we got fresh data
        if len(self.stops) > 0:
            self._save_stops_cache()

        logger.info(
            f"Transport service initialized: {len(self.stops)} stops, {len(self.lines)} lines"
        )

    # ------------------------------------------------------------------
    # Polling
    # ------------------------------------------------------------------
    async def poll_departures(self):
        """Poll all key stops concurrently and update the active trips snapshot."""
        new_trips: dict[str, dict[str, Any]] = {}

        async def poll_single(stop_name: str, stop_id: str):
            try:
                departures = await asyncio.wait_for(
                    self._monitor_stop(stop_name, DEPARTURE_LIMIT),
                    timeout=10,
                )
                dep_list = []

                for dep in departures:
                    scheduled = dep.scheduled
                    real_time = dep.real_time

                    # Compute delay in seconds
                    delay_seconds = 0
                    if scheduled and real_time:
                        delay_seconds = int((real_time - scheduled).total_seconds())

                    trip_id = dep.id or f"{dep.line}_{dep.direction}_{scheduled}"

                    dep_dict = {
                        "trip_id": trip_id,
                        "line": dep.line,
                        "direction": dep.direction or "",
                        "mode": dep.mode or "Tram",
                        "scheduled": scheduled,
                        "real_time": real_time,
                        "delay_seconds": delay_seconds,
                        "stop_id": stop_id,
                        "stop_name": stop_name,
                        "state": dep.state or "InTime",
                    }

                    if dep_dict["mode"] in ["Train", "SuburbanRailway"]:
                        continue

                    dep_list.append(dep_dict)

                    # Track this as an active trip — deduplication key
                    if trip_id not in new_trips:
                        new_trips[trip_id] = dep_dict
                    else:
                        # Merge stops seen at multiple key stops.
                        # Rule: earliest scheduled time = current stop; nearest later stop = next_stop.
                        existing = new_trips[trip_id]
                        if scheduled and existing["scheduled"]:
                            if scheduled < existing["scheduled"]:
                                # This dep is EARLIER → it becomes the current stop
                                # and the old base becomes the next_stop
                                old = existing
                                new_trips[trip_id] = dep_dict.copy()
                                new_trips[trip_id].update(
                                    next_stop_id=old["stop_id"],
                                    next_stop_name=old["stop_name"],
                                    next_scheduled=old["scheduled"],
                                    next_delay_seconds=old.get("delay_seconds", 0),
                                )
                                # Preserve any next_stop already on the old base if it was
                                # closer than the old base itself (shouldn't happen but safe)
                            elif scheduled > existing["scheduled"]:
                                # This dep is LATER → candidate for next_stop
                                # Only update if it is closer than any already-recorded next_stop
                                existing_next = existing.get("next_scheduled")
                                if existing_next is None or scheduled < existing_next:
                                    new_trips[trip_id].update(
                                        next_stop_id=stop_id,
                                        next_stop_name=stop_name,
                                        next_scheduled=scheduled,
                                        next_delay_seconds=delay_seconds,
                                    )

                self.departures_by_stop[stop_id] = dep_list

            except asyncio.TimeoutError:
                logger.warning(f"Timeout polling {stop_name}")
            except Exception as e:
                logger.warning(f"Error polling {stop_name}: {e}")

        # Poll all stops concurrently
        await asyncio.gather(
            *[poll_single(name, sid) for name, sid in KEY_STOPS],
            return_exceptions=True,
        )

        current_time = datetime.now(timezone.utc)
        to_delete = []

        # Update cache with new data
        for tid, tdata in new_trips.items():
            self.active_trips[tid] = tdata

        # Clean old data from cache
        for tid, tdata in self.active_trips.items():
            dt = tdata.get("scheduled")
            delay = tdata.get("delay_seconds", 0)
            if dt:
                adj = dt + timedelta(seconds=delay)
                if current_time - adj > timedelta(minutes=20):
                    to_delete.append(tid)

        for tid in to_delete:
            del self.active_trips[tid]

        logger.debug(f"Cache size: {len(self.active_trips)} active trips")

    def get_active_departures(self) -> list[dict[str, Any]]:
        """Return current active trip data for vehicle inference."""
        return list(self.active_trips.values())

    def get_stops(self) -> list[dict]:
        """Return all known stops."""
        return list(self.stops.values())

    def get_lines(self) -> list[dict]:
        """Return all known lines (without polylines — those come from route_service)."""
        result = []
        for line_id, line_data in self.lines.items():
            result.append({
                "id": line_data["id"],
                "name": line_data["name"],
                "mode": line_data["mode"],
                "directions": line_data["directions"],
            })
        return result
