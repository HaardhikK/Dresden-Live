"""
Lines API — GET /api/lines
"""
from fastapi import APIRouter
from services.transport_service import TransportService
from config import LINE_COLORS, DEFAULT_LINE_COLOR

router = APIRouter()

# Will be set by main.py on startup
transport_service: TransportService | None = None


@router.get("/api/lines")
async def get_lines():
    """Return all known DVB lines with colours."""
    if not transport_service:
        return []

    lines = transport_service.get_lines()
    result = []
    for line in lines:
        line_id = line["id"]
        result.append({
            "id": line_id,
            "name": line["name"],
            "mode": line["mode"],
            "color": LINE_COLORS.get(line_id, DEFAULT_LINE_COLOR),
            "directions": line.get("directions", []),
        })
    return result
