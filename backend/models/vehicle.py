"""
Vehicle data model — represents an inferred vehicle position.
"""
from pydantic import BaseModel
from typing import Optional


class Vehicle(BaseModel):
    """A single inferred vehicle position."""
    vehicle_id: str
    line_id: str
    line_name: str
    mode: str           # "Tram" or "Bus"
    lat: float
    lon: float
    heading: float      # Bearing in degrees (0 = north, 90 = east)
    direction: str      # Final destination name
    delay_seconds: int
    timestamp: str      # ISO 8601

    # Current and next stop info
    prev_stop: str
    next_stop: str
    progress: float     # 0.0 to 1.0 between prev and next stop

    # Segment geometry for client-side interpolation
    prev_stop_lat: Optional[float] = None
    prev_stop_lon: Optional[float] = None
    next_stop_lat: Optional[float] = None
    next_stop_lon: Optional[float] = None
    segment_duration_seconds: Optional[float] = None

    # Full polyline for client-side multi-segment interpolation
    # Each element is [lat, lon]. Sent so the frontend can follow
    # the actual curved route instead of a straight line.
    polyline: Optional[list[list[float]]] = None
    
    is_stale: bool = False
