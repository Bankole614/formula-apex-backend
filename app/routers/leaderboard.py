import json
import time
import uuid
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
import aiosqlite

from ..database import get_db
from ..models import LeaderboardSubmission, LeaderboardEntryResponse
from ..services.anti_cheat import validate_lap_time

router = APIRouter(prefix="/api/leaderboard", tags=["Leaderboards"])


@router.get("", response_model=List[LeaderboardEntryResponse])
async def get_leaderboard(
    track: str = Query(..., description="Track name (e.g. 'Default', 'Silverstone')"),
    limit: int = Query(50, ge=1, le=100),
    db: aiosqlite.Connection = Depends(get_db),
):
    """
    Fetch top lap records for a specific circuit, sorted by fastest lap time.
    """
    cursor = await db.execute(
        """
        SELECT id, track_name, driver_name, team_name, car_color, time_ticks,
               time_formatted, sectors_json, compound, has_ghost, created_at
        FROM leaderboards
        WHERE LOWER(track_name) = LOWER(?)
        ORDER BY time_ticks ASC
        LIMIT ?;
        """,
        (track.strip(), limit),
    )
    rows = await cursor.fetchall()

    results = []
    for r in rows:
        sectors = None
        if r["sectors_json"]:
            try:
                sectors = json.loads(r["sectors_json"])
            except Exception:
                sectors = None

        results.append(
            LeaderboardEntryResponse(
                id=r["id"],
                trackName=r["track_name"],
                driverName=r["driver_name"],
                teamName=r["team_name"] or "Apex GP",
                carColor=r["car_color"] or "#e10600",
                timeTicks=r["time_ticks"],
                timeFormatted=r["time_formatted"],
                sectors=sectors,
                compound=r["compound"] or "M",
                date=str(r["created_at"])[:10],
                hasGhost=bool(r["has_ghost"]),
            )
        )
    return results


@router.post("")
async def submit_lap_record(
    sub: LeaderboardSubmission,
    db: aiosqlite.Connection = Depends(get_db),
):
    """
    Submit a completed race / qualifying lap time. Validates against anti-cheat thresholds.
    """
    # 1. Anti-cheat validation
    if not validate_lap_time(sub.trackName, sub.timeTicks, sub.sectors):
        raise HTTPException(
            status_code=400,
            detail="Lap time failed physics validation check.",
        )

    # 2. Check compound code
    compound_code = "M"
    if isinstance(sub.compound, int):
        compound_map = {0: "S", 1: "M", 2: "H", 3: "W"}
        compound_code = compound_map.get(sub.compound, "M")
    elif isinstance(sub.compound, str):
        compound_code = sub.compound.upper()[:1]

    # 3. Insert record
    record_id = f"rec_{int(time.time() * 1000)}_{uuid.uuid4().hex[:6]}"
    sectors_str = json.dumps(sub.sectors) if sub.sectors else None
    ghost_str = json.dumps(sub.ghostData) if sub.ghostData else None
    has_ghost = 1 if sub.ghostData else 0

    await db.execute(
        """
        INSERT INTO leaderboards (
            id, track_name, driver_name, team_name, car_color,
            time_ticks, time_formatted, sectors_json, compound,
            has_ghost, ghost_data_json
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
        """,
        (
            record_id,
            sub.trackName.strip(),
            sub.driverName.strip(),
            sub.teamName or "Apex GP",
            sub.carColor or "#e10600",
            sub.timeTicks,
            sub.timeFormatted,
            sectors_str,
            compound_code,
            has_ghost,
            ghost_str,
        ),
    )
    await db.commit()

    return {
        "success": True,
        "recordId": record_id,
        "message": "Lap time recorded successfully.",
    }


@router.get("/ghost/{record_id}")
async def get_ghost_telemetry(
    record_id: str,
    db: aiosqlite.Connection = Depends(get_db),
):
    """
    Fetch full tick-by-tick ghost telemetry for ghost replay vs. other players worldwide.
    """
    cursor = await db.execute(
        "SELECT ghost_data_json, track_name, driver_name, time_formatted FROM leaderboards WHERE id = ?;",
        (record_id,),
    )
    row = await cursor.fetchone()
    if not row or not row["ghost_data_json"]:
        raise HTTPException(status_code=404, detail="Ghost telemetry not found for this record.")

    return {
        "recordId": record_id,
        "track": row["track_name"],
        "driver": row["driver_name"],
        "time": row["time_formatted"],
        "telemetry": json.loads(row["ghost_data_json"]),
    }

