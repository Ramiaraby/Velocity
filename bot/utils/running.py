"""Parsing, validation, and formatting for running activities."""

from decimal import Decimal, InvalidOperation
import re


def to_meters(distance: str) -> int:
    match = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*(km|k|m)\s*", distance.lower())
    if not match:
        raise ValueError("Distance must look like 5km or 1500m.")
    try:
        value = Decimal(match.group(1))
    except InvalidOperation as exc:
        raise ValueError("Invalid distance.") from exc
    meters = value * (1000 if match.group(2) in ("km", "k") else 1)
    if not meters.is_finite() or meters <= 0 or meters != meters.to_integral_value():
        raise ValueError("Distance must be a positive whole number of meters.")
    return int(meters)


def to_seconds(duration: str) -> int:
    parts = duration.strip().split(":")
    if len(parts) not in (2, 3) or not all(p.isascii() and p.isdigit() for p in parts):
        raise ValueError("Duration must be MM:SS or HH:MM:SS.")
    values = [int(part) for part in parts]
    if any(value >= 60 for value in values[1:]):
        raise ValueError("Seconds (and the minutes in HH:MM:SS) must be below 60.")
    seconds = sum(value * 60 ** i for i, value in enumerate(reversed(values)))
    if seconds <= 0:
        raise ValueError("Duration must be greater than zero.")
    return seconds


def format_duration(seconds: int) -> str:
    hours, remainder = divmod(seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours}:{minutes:02d}:{seconds:02d}" if hours else f"{minutes}:{seconds:02d}"


def format_distance(meters: int) -> str:
    return f"{meters / 1000:g} km"


def calculate_pace(meters: int, seconds: int) -> int:
    if meters <= 0:
        raise ValueError("Distance must be greater than zero.")
    return round(seconds * 1000 / meters)


def validate_run(name: str, distance: str, duration: str) -> tuple[str, int, int]:
    name = name.strip()
    if not 1 <= len(name) <= 20:
        raise ValueError("Run name must be between 1 and 20 characters.")
    meters = to_meters(distance)
    seconds = to_seconds(duration)
    if meters < 1000:
        raise ValueError("Runs must be at least 1 km.")
    if meters > 1_000_000:
        raise ValueError("Distance is too large for a single run.")
    pace = seconds * 1000 / meters
    if not 126 <= pace <= 1200:
        raise ValueError("Check your distance and time: pace must be between 2:06 and 20:00 per km.")
    return name, meters, seconds
