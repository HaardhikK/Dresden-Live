"""
Stops API — GET /api/stops
"""
from fastapi import APIRouter
from services.transport_service import TransportService

router = APIRouter()

# Will be set by main.py on startup
transport_service: TransportService | None = None


@router.get("/api/stops")
async def get_stops():
    """Return all known DVB stops with coordinates."""
    if not transport_service:
        return []
    stops = transport_service.get_stops()
    # Filter out stops without coordinates
    return [s for s in stops if s.get("lat", 0) != 0]
