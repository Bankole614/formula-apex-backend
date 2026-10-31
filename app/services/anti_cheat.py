from typing import List, Optional


def validate_lap_time(
    track_name: str,
    time_ticks: int,
    sectors: Optional[List[float]] = None,
) -> bool:
    """
    Validates lap submission against physical thresholds to reject impossible times / cheats.
    """
    # Absolute minimum physics threshold: impossible to complete any circuit in under 3.0s (180 ticks)
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

