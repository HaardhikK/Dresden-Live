"""
Dresden Digital Twin — Backend Entry Point

FastAPI application with:
  - Background polling of DVB transport data
  - Vehicle position inference on each poll cycle
  - REST API endpoints for stops, lines, and vehicles
  - WebSocket endpoint for real-time vehicle updates

Startup is non-blocking: the server becomes available immediately
while DVB data loads in the background.
"""
import asyncio
import logging
import sys
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import POLL_INTERVAL_SECONDS, CORS_ORIGINS
from services.transport_service import TransportService
from services.route_service import RouteService
from services.vehicle_inference import VehicleInferenceService
from services.gtfs_service import GtfsService
from api import stops_api, lines_api, vehicles_api

# --- Logging ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)

# --- Shared services (created in lifespan) ---
transport_service: TransportService | None = None
route_service: RouteService | None = None
inference_service: VehicleInferenceService | None = None
gtfs_service: GtfsService | None = None

# --- Background polling task ---
polling_task: asyncio.Task | None = None


async def poll_and_infer():
    """Background loop: poll DVB data → infer vehicle positions → broadcast."""
    global transport_service, inference_service
    while True:
        try:
            if transport_service and inference_service:
                # 1. Poll DVB for fresh departure data
                await transport_service.poll_departures()

                # 2. Run vehicle inference
                departures = transport_service.get_active_departures()
                vehicles = await inference_service.update_vehicles(
                    departures, transport_service.stops
                )

                logger.info(f"Inferred {len(vehicles)} vehicle positions")

                # 3. Broadcast to WebSocket clients
                await vehicles_api.broadcast_vehicles()

        except Exception as e:
            logger.error(f"Poll cycle error: {e}")

        await asyncio.sleep(POLL_INTERVAL_SECONDS)


async def warmup_task():
    """
    Non-blocking warmup: initialises DVB data and runs the first poll
    in the background so the server is available instantly.
    """
    global transport_service, inference_service
    try:
        logger.info("Loading DVB stop and line data (background)...")
        await transport_service.initialize()
        
        logger.info("Downloading and processing static GTFS data...")
        await gtfs_service.initialize()

        logger.info("Running initial departure poll...")
        await transport_service.poll_departures()
        departures = transport_service.get_active_departures()
        vehicles = await inference_service.update_vehicles(
            departures, transport_service.stops
        )
        logger.info(f"Initial poll complete: {len(vehicles)} vehicles found")
        await vehicles_api.broadcast_vehicles()
    except Exception as e:
        logger.error(f"Warmup error: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown lifecycle."""
    global transport_service, route_service, inference_service, polling_task

    logger.info("=" * 60)
    logger.info("  Dresden Digital Twin — Backend Starting")
    logger.info("=" * 60)

    # Create services
    transport_service = TransportService()
    route_service = RouteService()
    gtfs_service = GtfsService()
    inference_service = VehicleInferenceService(route_service, gtfs_service)

    # Wire services into API modules
    stops_api.transport_service = transport_service
    lines_api.transport_service = transport_service
    vehicles_api.inference_service = inference_service

    # Non-blocking warmup — server is available instantly
    asyncio.create_task(warmup_task())

    # Start background polling (will wait until warmup populates data)
    polling_task = asyncio.create_task(poll_and_infer())
    logger.info(f"Background polling started (every {POLL_INTERVAL_SECONDS}s)")
    logger.info("Backend ready! API at http://localhost:8000")

    yield

    # Shutdown
    logger.info("Shutting down...")
    if polling_task:
        polling_task.cancel()
        try:
            await polling_task
        except asyncio.CancelledError:
            pass
    if route_service:
        await route_service.close()
    logger.info("Backend stopped.")


# --- FastAPI app ---
app = FastAPI(
    title="Dresden Digital Twin",
    description="Live transit visualization with vehicle tracking",
    version="0.2.0",
    lifespan=lifespan,
)

# CORS — allow the frontend dev server
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount API routers
app.include_router(stops_api.router)
app.include_router(lines_api.router)
app.include_router(vehicles_api.router)


@app.get("/")
async def root():
    """Health check / info endpoint."""
    vehicle_count = len(inference_service.get_vehicles()) if inference_service else 0
    stop_count = len(transport_service.get_stops()) if transport_service else 0
    last_update = inference_service.last_update_utc if inference_service else ""
    return {
        "service": "Dresden Digital Twin — Backend",
        "status": "running",
        "vehicles_tracked": vehicle_count,
        "stops_loaded": stop_count,
        "last_update_utc": last_update,
    }


@app.get("/api/time")
async def get_time():
    """Return current server UTC time and last inference timestamp."""
    last_update = inference_service.last_update_utc if inference_service else ""
    return {
        "server_utc": datetime.now(timezone.utc).isoformat(),
        "last_update_utc": last_update,
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
