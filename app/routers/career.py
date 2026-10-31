import json
from fastapi import APIRouter, Depends, HTTPException, status
import aiosqlite

from ..database import get_db
from ..schemas.career import CareerSyncRequest, CareerProfileResponse
from ..config import settings
from ..core.security import create_player_token, verify_player_token

router = APIRouter(prefix="/api/career", tags=["Career Cloud Sync"])


@router.post("/token")
async def generate_player_token(user_id: str, driver_name: str):
    """
    Issue a signed JWT authentication token for a player's cloud profile.
    """
    if len(user_id) < 3:
        raise HTTPException(status_code=400, detail="Invalid user_id.")
    token = create_player_token(user_id.strip(), driver_name.strip())
    return {"token": token, "userId": user_id, "tokenType": "Bearer"}


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
    Validates token if provided or if REQUIRE_AUTH_FOR_CAREER_SYNC is enabled.
    """
    if user_id.strip() != req.userId.strip():
        raise HTTPException(
            status_code=400,
            detail="Path parameter userId does not match request body userId.",
        )

    # Security check: if token provided or strictly required in production
    if req.authToken or settings.REQUIRE_AUTH_FOR_CAREER_SYNC:
        if not req.authToken:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication token required to sync cloud profile.",
            )
        payload = verify_player_token(req.authToken)
        if not payload or payload.get("sub") != user_id.strip():
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Invalid or expired player auth token.",
            )

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
