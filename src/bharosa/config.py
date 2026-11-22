import os
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:  # dotenv is optional at import time
    pass


def _get(name: str, default: str) -> str:
    return os.environ.get(name, default)


TICKETS_CSV = Path(_get("TICKETS_CSV", "data/raw/October-Delhi.csv"))
GTFS_DIR = Path(_get("GTFS_DIR", "data/raw/gtfs"))
GPS_DIR = Path(_get("GPS_DIR", "data/raw/gps"))
OUT_DIR = Path(_get("OUT_DIR", "data/out"))
INTERIM_DIR = Path("data/interim")

MIN_TICKETS_PER_CELL = int(_get("MIN_TICKETS_PER_CELL", "30"))
BOOTSTRAP_SAMPLES = int(_get("BOOTSTRAP_SAMPLES", "500"))
PASS_HOLDER_UPLIFT = (
    float(_get("PASS_HOLDER_UPLIFT_LOW", "1.0")),
    float(_get("PASS_HOLDER_UPLIFT_HIGH", "1.6")),
)
# Share of all bus tickets present in this dataset (event page: "only 3-4%"). Range, not a fact.
SAMPLE_RATE = (
    float(_get("SAMPLE_RATE_LOW", "0.03")),
    float(_get("SAMPLE_RATE_HIGH", "0.04")),
)
# Use buses seen on tickets (vehicle_number) as a floor for trip counts: 1 = yes, 0 = scheduled only.
OBSERVED_TRIPS = _get("OBSERVED_TRIPS", "1") == "1"
# Capacity is deliberately unset: source it from DTC/DIMTS, do not guess.
CAPACITY_SEATS = _get("CAPACITY_SEATS", "")
CAPACITY_STANDING = _get("CAPACITY_STANDING", "")
