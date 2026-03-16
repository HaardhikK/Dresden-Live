"""
Vehicles API — GET /api/vehicles + WS /ws/vehicles
"""
import asyncio
import json
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from services.vehicle_inference import VehicleInferenceService

logger = logging.getLogger(__name__)

router = APIRouter()

# Will be set by main.py on startup
inference_service: VehicleInferenceService | None = None

# Active WebSocket connections
ws_connections: list[WebSocket] = []


@router.get("/api/vehicles")
async def get_vehicles():
    """Return all currently inferred vehicle positions."""
    if not inference_service:
        return []
    vehicles = inference_service.get_vehicles()
    return [v.model_dump() for v in vehicles]


@router.websocket("/ws/vehicles")
async def websocket_vehicles(websocket: WebSocket):
    """
    WebSocket endpoint for real-time vehicle position updates.
    Sends vehicle_update messages whenever positions are recomputed.
    """
    await websocket.accept()
    ws_connections.append(websocket)
    logger.info(f"WebSocket client connected. Total: {len(ws_connections)}")

    try:
        # Keep the connection alive; the broadcast loop sends data
        while True:
            # Wait for client messages (keepalive pings)
            try:
                data = await asyncio.wait_for(websocket.receive_text(), timeout=60)
            except asyncio.TimeoutError:
                # Send a ping to keep connection alive
                try:
                    await websocket.send_json({"type": "ping"})
                except Exception:
                    break
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.debug(f"WebSocket error: {e}")
    finally:
        if websocket in ws_connections:
            ws_connections.remove(websocket)
        logger.info(f"WebSocket client disconnected. Total: {len(ws_connections)}")


async def broadcast_vehicles():
    """Send current vehicle data to all connected WebSocket clients."""
    if not inference_service:
        return

    vehicles = inference_service.get_vehicles()
    if not vehicles:
        return

    payload = json.dumps({
        "type": "vehicle_update",
        "count": len(vehicles),
        "vehicles": [v.model_dump() for v in vehicles],
    })

    disconnected = []
    for ws in ws_connections:
        try:
            await ws.send_text(payload)
        except Exception:
            disconnected.append(ws)

    for ws in disconnected:
        if ws in ws_connections:
            ws_connections.remove(ws)
