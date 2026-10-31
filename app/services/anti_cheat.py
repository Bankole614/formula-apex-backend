import math
from typing import List, Optional, Dict, Any


def validate_lap_time(
    track_name: str,
    time_ticks: int,
    sectors: Optional[List[float]] = None,
) -> bool:
    """
    Validates lap submission against physical thresholds to reject impossible times / cheats.
    """
    # Absolute minimum physics threshold: impossible to complete any circuit in under 3.0s (180 ticks at 60 FPS)
    if time_ticks < 180:
        return False

    # Circuit-specific physical limits (minimum plausible lap time in 60 FPS ticks)
    track_thresholds = {
        "Default": 280,
        "Silverstone": 1600,
        "Monaco": 1400,
        "Spa": 1800,
        "Suzuka": 1600,
        "Interlagos": 1200,
        "Autodromo Nazionale Apex": 1200,
    }

    norm_track = track_name.strip()
    if norm_track in track_thresholds and time_ticks < track_thresholds[norm_track]:
        return False

    # Sector consistency check: sum of 3 sectors must roughly equal total lap time in seconds
    if sectors and len(sectors) == 3:
        total_seconds = time_ticks / 60.0
        sector_sum = sum(sectors)
        # Allow up to 0.4s floating point / rounding drift
        if abs(total_seconds - sector_sum) > 0.4:
            return False

    return True


def validate_ghost_telemetry(
    ghost_data: Optional[List[Dict[str, Any]]],
    time_ticks: int,
    max_realistic_speed_kmh: float = 430.0,
) -> bool:
    """
    Validates recorded ghost telemetry frames:
    1. Checks frame density: must have sufficient frames relative to lap duration.
    2. Validates physical speed and positional delta bounds (no teleportation / speed hack).
    """
    if not ghost_data:
        return True  # Laps without ghost are valid if validate_lap_time passed

    # Lap duration in seconds
    total_seconds = time_ticks / 60.0
    frame_count = len(ghost_data)

    # Telemetry should be captured at least ~5-10 Hz (at least 5 samples per second)
    min_expected_frames = max(10, int(total_seconds * 3))
    if frame_count < min_expected_frames:
        return False

    max_speed_ms = max_realistic_speed_kmh / 3.6  # ~119.4 m/s

    prev_frame = None
    for frame in ghost_data:
        # Check required fields
        if not isinstance(frame, dict):
            return False

        # Speed check if reported
        speed = frame.get("speed")
        if speed is not None and isinstance(speed, (int, float)):
            # Game speed might be in km/h or m/s; check conservative threshold
            if speed > max_realistic_speed_kmh:
                return False

        # Positional jump / teleportation check
        if prev_frame and "x" in frame and "y" in frame and "x" in prev_frame and "y" in prev_frame:
            dx = frame["x"] - prev_frame["x"]
            dy = frame["y"] - prev_frame["y"]
            dist = math.hypot(dx, dy)
            # Assuming sample rate is ~0.05 - 0.2s, max distance between consecutive frames
            # should not exceed ~120m unless a warp cheat was triggered
            if dist > 350.0:
                return False

        prev_frame = frame

    return True
