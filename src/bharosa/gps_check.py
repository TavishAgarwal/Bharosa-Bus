"""Optional: dwell/bunching from 2-3 GPS days as an independent crowding signal; flag disagreements."""
from . import config  # noqa: F401


def run() -> None:
    raise NotImplementedError("gps_check: see TASKS.md (I-F9)")


if __name__ == "__main__":
    run()
