"""
Dresden Digital Twin — Backend Configuration
"""

# --- Polling ---
POLL_INTERVAL_SECONDS = 10          # How often we poll DVB for departures
DEPARTURE_LIMIT = 30                # Max departures per stop per poll

# --- Server ---
HOST = "0.0.0.0"
PORT = 8000
CORS_ORIGINS = ["http://localhost:5173", "http://localhost:3000", "http://127.0.0.1:5173"]

# --- Dresden centre (for map default) ---
DRESDEN_CENTER_LAT = 51.0504
DRESDEN_CENTER_LON = 13.7373

# --- Key stops to monitor ---
# We poll a curated set of major Dresden stops that cover all tram/bus lines.
# Each entry: (stop_name, stop_id)
KEY_STOPS = [
    ("Postplatz", "33000037"),
    ("Pirnaischer Platz", "33000038"),
    ("Albertplatz", "33000005"),
    ("Hauptbahnhof", "33000028"),
    ("Bahnhof Neustadt", "33000016"),
    ("Straßburger Platz", "33000036"),
    ("Lennéplatz", "33000035"),
    ("Carolaplatz", "33000491"),
    ("Fetscherplatz", "33000006"),
    ("Sachsenplatz", "33000039"),
    ("Tharandter Straße", "33000144"),
    ("Nürnberger Platz", "33000013"),
    ("Walpurgisstraße", "33000042"),
    ("Blasewitzer Straße", "33000495"),
    ("Schillerplatz", "33000034"),
    ("Prager Straße", "33000033"),
    ("Zwinglistraße", "33000044"),
    ("Helmholtzstraße", "33000742"),
    ("Mickten", "33000132"),
    ("Bühlau", "33000056"),
    ("Kleinzschachwitz", "33000069"),
    ("Laubegast", "33000072"),
    ("Löbtau", "33000082"),
    ("Plauen", "33000008"),
    ("Coschütz", "33000061"),
    ("Pennrich", "33000099"),
    ("Gorbitz", "33000078"),
    ("Prohlis", "33000105"),
    ("Leutewitz", "33000081"),
    ("Wilder Mann", "33000140"),
    ("Bahnhof Mitte", "33000015"),
    ("Wasaplatz", "33000043"),
    ("Trachenberger Platz", "33000160"),
    ("Münchner Platz", "33000012"),
    ("Bischofsweg", "33000017"),
    ("Altpieschen", "33000127"),
    ("Hellerau", "33000091"),
    ("Webergasse", "33000032"),
    ("Hp Freiberger Straße", "33000143"),
    ("Weißeritzstraße", "33000142"),
    ("St.-Benno-Gymnasium", "33000080"),
]

# --- Line colours (DVB official-ish) ---
LINE_COLORS = {
    "1": "#E2001A",
    "2": "#00A650",
    "3": "#F39200",
    "4": "#E2001A",
    "6": "#009FE3",
    "7": "#CE1266",
    "8": "#009640",
    "9": "#A62B44",
    "10": "#006AB3",
    "11": "#EE7F00",
    "12": "#A12944",
    "13": "#8B6E45",
    "61": "#009FE3",
    "62": "#009FE3",
    "63": "#009FE3",
    "64": "#009FE3",
    "65": "#009FE3",
    "66": "#009FE3",
    "72": "#8B6E45",
    "73": "#8B6E45",
    "74": "#8B6E45",
    "75": "#8B6E45",
    "76": "#8B6E45",
    "77": "#8B6E45",
    "79": "#8B6E45",
    "80": "#8B6E45",
    "81": "#8B6E45",
    "83": "#8B6E45",
    "84": "#8B6E45",
    "85": "#8B6E45",
    "88": "#8B6E45",
    "89": "#8B6E45",
    "90": "#8B6E45",
    "92": "#8B6E45",
}

# Default colour for unknown lines
DEFAULT_LINE_COLOR = "#888888"

# --- OSRM (for route geometry) ---
OSRM_BASE_URL = "https://router.project-osrm.org"

# --- Vehicle inference ---
# Minimum seconds between two stops for inference (avoids division-by-zero)
MIN_SEGMENT_DURATION_SECONDS = 30
# Maximum vehicles to track simultaneously
MAX_VEHICLES = 300
