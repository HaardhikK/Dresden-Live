# Dresden Live ## Transit Map

I came across the `dvb` Python library one evening; it wraps the public departure API for Dresdner Verkehrsbetriebe (DVB), Dresden's public transit operator. There's no real GPS feed available, so I thought it would be fun to see if I could fake one. This is the result: a live 3D map of Dresden that infers tram and bus positions in real time from schedule data, routing geometry, and a bit of math.

It is a side project I built for fun. Not production software, not commercial, just something cool to look at.

---

<img src="demo.gif" alt="Dresden Transit Live Map Demo" width="100%">

---

## How it works

The backend polls DVB departure boards at around 40 major stops every 10 seconds. For each active trip it figures out where the vehicle probably is right now based on:

- the scheduled departure time and any reported delay
- the route geometry fetched from OSRM (the public routing engine)
- linear interpolation along that geometry based on elapsed time

The frontend picks up positions over WebSocket and animates them smoothly between server updates using a `requestAnimationFrame` loop. The whole thing runs 90 seconds in the past so the history buffer has time to fill before anything is shown on screen.

Trams use the `foot` routing profile in OSRM since tram tracks mostly follow pedestrian paths in OpenStreetMap. Buses use the `driving` profile.

**Features**

- Real-time inferred positions for trams and buses across Dresden
- 3D extruded vehicle boxes with neon trip trails (Deck.GL)
- Anti-bunching: vehicles fan out visibly when they bunch at stops instead of stacking
- Startup countdown while the 90-second history buffer populates
- WebSocket primary feed with REST polling fallback
- Stop markers with live departure data

---

## Sources and credits

**dvb** (https://github.com/kiliankoe/dvb) — the Python library that makes querying DVB departure data possible. Without this the whole project does not exist.

**OSRM** (https://project-osrm.org) — the open source routing engine used to get realistic route geometry between stops. Using the public demo server for this project.

**MapLibre GL** — open source map rendering.

**Deck.GL** — the WebGL overlay layer for the vehicle animation.

**OpenStreetMap** contributors — the underlying map data everything runs on.

This project is purely a personal experiment. It is not affiliated with DVB, not intended for commercial use, and not meant to be a replacement for any official tracker. If you are using the DVB or OSRM public APIs for something similar, be reasonable with request rates.

---

## Architecture and fallbacks

The position of any vehicle between two known stops is estimated, not measured. A few things worth knowing:

- Only major hubs are polled (around 40 stops) as a deliberate trade-off to avoid hammering the DVB API. Vehicles between minor stops have their travel time estimated mathematically.
- When a trip is visible at two polled stops simultaneously the system picks the earlier one as the current stop and the later one as the next stop. This is order-independent regardless of which network response arrives first.
- If no next-stop data exists for a trip the vehicle still moves — it departs in a direction derived from the trip ID hash so vehicles spread out rather than all going to the same point. These fallback vehicles disappear after 3 minutes.
- Route polylines are cached in memory so OSRM is not hit on every poll cycle.
- Stop coordinates are cached to `stops_cache.json` so they survive restarts without re-fetching.

---

## Running it locally

Backend (FastAPI, Python 3.14):

```bash
cd backend
../.venv/Scripts/python -m uvicorn main:app --reload --port 8000
```

Frontend (React + Vite):

```bash
cd frontend
npm run dev
```

Wait about 90 seconds after the backend starts before vehicles appear. The frontend shows a countdown.

---

## Known problems and things I want to fix eventually

**3D vehicle models** — I tried replacing the extruded boxes with actual 3D tram models via Three.js but it was too heavy and tanked the frame rate. Shelved for now.

**Platform accuracy** — the map treats each station as a single point. It does not know about individual platforms, so a tram going to Hauptbahnhof track 3 and a bus going to the stop outside look identical positionally.

**Terminus behaviour** — vehicles do not know to stop outside a terminal. Trams currently drive straight through Hauptbahnhof instead of stopping at the right point outside it.

**German language toggle** — easy to add, I just ran out of patience after debugging everything else.

**Trains** — DB regional trains use a completely different API and I have not tackled that yet.

**Reverse the history buffer** — right now the app waits 90 seconds on startup because it needs historical data to show anything sensible. A better approach would be to pre-fetch 90 seconds of past departures on startup instead of waiting. I have not done this yet because I did not want to read deep into the API docs and risk getting rate-limited.

**Minor stops** — only major hubs are queried directly. Everything else is estimated. This works well enough but it means vehicles disappear after passing the last known stop rather than continuing to their actual destination.

**Hosting** — I tried. I got tired.
