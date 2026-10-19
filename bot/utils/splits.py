"""Sport-aware split parsing and validation; pure functions for unit testing."""

from math import ceil
import re

from bot.utils.running import format_duration, to_seconds

# A reasonably sized Discord modal can carry at most 4000 text characters.
MAX_SPLITS = 100
STEP_METERS = {"running": 1000, "cycling": 1000, "swimming": 100}


def split_step(sport: str) -> int:
    if sport not in STEP_METERS:
        raise ValueError("Invalid sport.")
    return STEP_METERS[sport]


def expected_segments(sport: str, meters: int) -> list[int]:
    step = split_step(sport)
    if meters <= 0:
        raise ValueError("Activity distance must be positive.")
    count = ceil(meters / step)
    if count > MAX_SPLITS:
        raise ValueError(
            f"Split editor supports up to {MAX_SPLITS} intervals; "
            "try a shorter activity or import fewer splits later."
        )
    return [min(step, meters - i * step) for i in range(count)]


def parse_manual_splits(text: str) -> list[int]:
    """One split time per line. Also accepts indexed rows like '1 5:12'.

    A time is the actual duration of that interval, NOT cumulative elapsed
    duration; swimming is always 100m intervals (last interval may be shorter).
    """
    raw = text.replace(",", "\n").replace(";", "\n")
    rows = [row.strip() for row in raw.splitlines() if row.strip()]
    if not rows:
        raise ValueError("Enter at least one split time, one per line.")
    if len(rows) > MAX_SPLITS:
        raise ValueError(f"At most {MAX_SPLITS} split times may be entered.")
    result = []
    indexes = []
    for row in rows:
        match = re.fullmatch(r"(?:(\d{1,3})\s*(?:[.)|\-]\s*)?)?(\d{1,3}:[0-5]\d(?::[0-5]\d)?)", row)
        if not match:
            raise ValueError(
                f"Invalid split '{row[:40]}'. Use one time per line, e.g. 5:12."
            )
        if match.group(1):
            indexes.append(int(match.group(1)))
        elif indexes:
            raise ValueError("Either number every row or leave every row unnumbered.")
        result.append(to_seconds(match.group(2)))
    if indexes and indexes != list(range(1, len(rows) + 1)):
        raise ValueError("Split numbers must be consecutive, starting from 1.")
    return result


def validate_splits(
    sport: str, meters: int, total_seconds: int, segments_seconds: list[int]
) -> list[tuple[int, int]]:
    lengths = expected_segments(sport, meters)
    if len(lengths) != len(segments_seconds):
        unit = "100 m" if sport == "swimming" else "1 km"
        raise ValueError(
            f"Expected {len(lengths)} split times for {meters:g} m "
            f"({unit} segments, including a possible partial final segment); "
            f"got {len(segments_seconds)}."
        )
    if any(seconds <= 0 or seconds > 24 * 3600 for seconds in segments_seconds):
        raise ValueError("Every interval must have a positive, realistic duration.")
    # Compare moving time with split time totals, allowing small timing differences.
    # Display the actual difference on error rather than silently treating them as proof.
    split_total = sum(segments_seconds)
    tolerance = max(15, round(total_seconds * 0.03))
    if abs(split_total - total_seconds) > tolerance:
        raise ValueError(
            f"Split times add up to {format_duration(split_total)} but activity "
            f"time is {format_duration(total_seconds)}. They should be within "
            f"{tolerance} seconds. Check your screenshot or edit the entries."
        )
    return list(zip(lengths, segments_seconds))


def display_split(sport: str, meters: int, seconds: int) -> str:
    """Show interval duration and normalized pace/speed, including partial segments."""
    if meters <= 0 or seconds <= 0:
        return "—"
    pace_unit_m = split_step(sport)
    scaled = round(seconds * pace_unit_m / meters)
    pace_label = "/100m" if sport == "swimming" else "/km"
    if sport == "cycling":
        speed = meters * 3.6 / seconds
        return f"{format_duration(seconds)}  ·  {speed:.1f} km/h"
    return f"{format_duration(seconds)}  ·  {format_duration(scaled)} {pace_label}"


# OCR is an opt-in suggestion: we only accept visibly indexed rows. We never
# auto-commit results; the runner confirms the preview first.
_OCR_ROW = re.compile(
    r"^\s*(?:lap\s*|km\s*)?(\d{1,4})\s*(?:m|km)?\s*"
    r"(?:[|:\-\u2013\u2014]|\s)+"
    r"(\d{1,3}:[0-5]\d(?::[0-5]\d)?)(?:\s*/\s*(?:km|100\s*m))?",
    flags=re.IGNORECASE,
)


def parse_ocr_rows(raw_text: str, sport: str, activity_meters: int) -> list[int]:
    """Extract sequential lap rows from OCR output; reject ambiguous layouts."""
    expected = expected_segments(sport, activity_meters)
    rows = []
    for line in raw_text.splitlines():
        match = _OCR_ROW.match(line)
        if not match:
            continue
        try:
            seconds = to_seconds(match.group(2))
        except ValueError:
            continue
        rows.append((int(match.group(1)), seconds))
    if len(rows) > MAX_SPLITS:
        raise ValueError("Too many candidate OCR rows; crop to the split table.")
    numbers = [row[0] for row in rows]
    count = len(expected)
    indices = list(range(1, count + 1))
    cumulative = list(range(split_step(sport), step_multiple(count, sport) + 1,
                            split_step(sport)))
    if len(rows) != count or numbers not in (indices, cumulative):
        unit = "100 m" if sport == "swimming" else "kilometer"
        raise ValueError(
            f"Could not reliably find {count} ordered {unit} rows. "
            "Crop the screenshot to its split table or enter the times manually."
        )
    return [seconds for _, seconds in rows]


def step_multiple(count: int, sport: str) -> int:
    return count * split_step(sport)
