"""
Data model for a transit line.
"""
from pydantic import BaseModel


class Line(BaseModel):
    id: str
    name: str
    mode: str           # "Tram" or "CityBus"
    color: str          # Hex colour, e.g. "#E2001A"
    directions: list[str] = []
    stops: list[str] = []               # Ordered stop IDs
    polyline: list[list[float]] = []    # [[lat, lon], ...] full route geometry
