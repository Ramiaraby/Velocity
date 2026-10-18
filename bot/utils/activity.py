"""Shared discipline-specific validation, metrics and labels."""

from bot.utils.evidence import validate_elevation
from bot.utils.running import (
    calculate_pace, format_distance, format_duration,
    to_meters, to_seconds, validate_run,
)

SPORT_LABELS = {"running": "Running", "cycling": "Cycling", "swimming": "Swimming"}
SPORT_ICONS = {"running": "🏃", "cycling": "🚴", "swimming": "🏊"}


def validate_activity(
    sport: str, name: str, distance: str, duration: str,
    *, elevation_m: int | None = None,
    swim_type: str | None = None, pool_length_m: int | None = None,
    notes: str | None = None,
) -> tuple[str, int, int, int | None, str | None, int | None, str | None]:
    """Return normalized fields; validate discipline-appropriate optional data."""
    if sport not in SPORT_LABELS:
        raise ValueError("Unknown sport.")
    name = name.strip()
    if sport == "running":
        name, meters, seconds = validate_run(name, distance, duration)
    else:
        if not 1 <= len(name) <= 20:
            raise ValueError("Activity name must be 1–20 characters.")
        meters, seconds = to_meters(distance), to_seconds(duration)
        if sport == "cycling":
            if not 1000 <= meters <= 1_000_000:
                raise ValueError("Cycling distances must be between 1 and 1000 km.")
            km_per_hour = meters * 3.6 / seconds
            if not 1 <= km_per_hour <= 150:
                raise ValueError("Check your distance and duration: cycling speed is unusual.")
        else:
            if not 25 <= meters <= 100_000:
                raise ValueError("Swimming distances must be between 25 m and 100 km.")
            secs_per_100m = seconds * 100 / meters
            if not 30 <= secs_per_100m <= 3600:
                raise ValueError("Check your distance and duration: swimming pace is unusual.")

    elevation_m = validate_elevation(elevation_m)
    if sport == "swimming":
        if elevation_m is not None:
            raise ValueError("Elevation gain is not used for swimming.")
        swim_type = swim_type or "pool"
        if swim_type not in ("pool", "open_water"):
            raise ValueError("Swimming type must be pool or open_water.")
        if swim_type == "open_water":
            if pool_length_m is not None:
                raise ValueError("Pool length is only for pool swimming.")
        else:
            if pool_length_m is not None and (
                not 10 <= pool_length_m <= 100 or meters % pool_length_m
            ):
                raise ValueError("Pool length must be 10–100 m and divide your distance exactly.")
    else:
        if swim_type is not None or pool_length_m is not None:
            raise ValueError("Swimming options are only available for swimming.")
    if notes is not None:
        notes = notes.strip() or None
        if notes is not None and len(notes) > 200:
            raise ValueError("Notes must be at most 200 characters.")
    return name, meters, seconds, elevation_m, swim_type, pool_length_m, notes


def activity_metric(sport: str, meters: int, seconds: int) -> str:
    if meters <= 0 or seconds <= 0:
        return "—"
    if sport == "cycling":
        return f"{meters * 3.6 / seconds:.1f} km/h"
    if sport == "swimming":
        return f"{format_duration(round(seconds * 100 / meters))} /100m"
    return f"{format_duration(calculate_pace(meters, seconds))} /km"


def summary_metric(sport: str, meters: int, seconds: int) -> str:
    return activity_metric(sport, meters, seconds)


def activity_display(sport: str, meters: int, seconds: int) -> str:
    return (
        f"{format_distance(meters)} · {format_duration(seconds)} · "
        f"{activity_metric(sport, meters, seconds)}"
    )
