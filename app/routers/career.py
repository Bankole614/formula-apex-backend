import json
from fastapi import APIRouter, Depends, HTTPException
import aiosqlite

from ..database import get_db
from ..models import CareerSyncRequest, CareerProfileResponse

router = APIRouter(prefix="/api/career", tags=["Career Cloud Sync"])


@router.get("/{user_id}", response_model=CareerProfileResponse)
async def get_career_profile(
    user_id: str,
    db: aiosqlite.Connection = Depends(get_db),
):
    """
    Fetch career mode progression for a player across devices.
    """
    cursor = await db.execute(
        """
        SELECT user_id, driver_name, team_id, level, xp, rd_points,
               upgrades_json, stats_json, updated_at
        FROM career_profiles
        WHERE user_id = ?;
        """,
        (user_id.strip(),),
    )
    row = await cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Career profile not found for this user.")

    upgrades = json.loads(row["upgrades_json"]) if row["upgrades_json"] else {}
    stats = json.loads(row["stats_json"]) if row["stats_json"] else {}

    return CareerProfileResponse(
        userId=row["user_id"],
        driverName=row["driver_name"],
        teamId=row["team_id"] or "scuderia",
        level=row["level"] or 1,
        xp=row["xp"] or 0,
        rdPoints=row["rd_points"] or 0,
        upgrades=upgrades,
        stats=stats,
        updatedAt=str(row["updated_at"]),
    )


@router.post("/{user_id}/sync")
async def sync_career_profile(
    user_id: str,
    req: CareerSyncRequest,
    db: aiosqlite.Connection = Depends(get_db),
):
    """
    Save and sync Career driver level, XP, R&D upgrades, and points.
    """
    upgrades_str = json.dumps(req.upgrades)
    stats_str = json.dumps(req.stats)

    await db.execute(
        """
        INSERT INTO career_profiles (
            user_id, driver_name, team_id, level, xp, rd_points,
            upgrades_json, stats_json, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(user_id) DO UPDATE SET
            driver_name = excluded.driver_name,
            team_id = excluded.team_id,
            level = MAX(career_profiles.level, excluded.level),
            xp = MAX(career_profiles.xp, excluded.xp),
            rd_points = excluded.rd_points,
            upgrades_json = excluded.upgrades_json,
            stats_json = excluded.stats_json,
            updated_at = CURRENT_TIMESTAMP;
        """,
        (
            user_id.strip(),
            req.driverName.strip(),
            req.teamId,
            req.level,
            req.xp,
            req.rdPoints,
            upgrades_str,
            stats_str,
        ),
    )
    await db.commit()

    return {
        "success": True,
        "userId": user_id,
        "message": "Career cloud state synced successfully.",
    }

