import json
import time
import uuid
from typing import List
from fastapi import APIRouter, Depends, HTTPException, Query
import aiosqlite

from ..database import get_db
from ..schemas.tracks import CommunityTrackSubmission, CommunityTrackResponse
from ..core.rate_limit import rate_limit_submissions, rate_limit_reactions

router = APIRouter(prefix="/api/community-tracks", tags=["Community Circuits"])


@router.get("", response_model=List[CommunityTrackResponse])
async def list_community_tracks(
    sort: str = Query("popular", description="'popular' or 'newest'"),
    limit: int = Query(30, ge=1, le=100),
    db: aiosqlite.Connection = Depends(get_db),
):
    """
    List user-created circuits published to the Community Paddock.
    """
    order_by = "likes DESC, created_at DESC" if sort == "popular" else "created_at DESC"
    cursor = await db.execute(
        f"""
        SELECT id, name, author, width, biome, control_json, pit_config_json,
               scenery_json, description, likes, created_at
        FROM community_tracks
        ORDER BY {order_by}
        LIMIT ?;
        """,
        (limit,),
    )
    rows = await cursor.fetchall()

    tracks = []
    for r in rows:
        control_pts = json.loads(r["control_json"]) if r["control_json"] else []
        pit_cfg = json.loads(r["pit_config_json"]) if r["pit_config_json"] else None
        scenery = json.loads(r["scenery_json"]) if r["scenery_json"] else None

        tracks.append(
            CommunityTrackResponse(
                id=r["id"],
                name=r["name"],
                author=r["author"],
                width=r["width"] or 60.0,
                biome=r["biome"] or "temperate",
                control=control_pts,
                pitConfig=pit_cfg,
                scenery=scenery,
                description=r["description"] or "Custom community layout.",
                date=str(r["created_at"])[:10],
                likes=r["likes"] or 0,
            )
        )
    return tracks


@router.post("", dependencies=[Depends(rate_limit_submissions)])
async def publish_community_track(
    sub: CommunityTrackSubmission,
    db: aiosqlite.Connection = Depends(get_db),
):
    """
    Publish a custom-designed track layout from Circuit Architect to the Community Hub.
    """
    if len(sub.control) < 4:
        raise HTTPException(
            status_code=400,
            detail="A circuit requires at least 4 control points to form a closed racing loop.",
        )

    track_id = f"trk_{int(time.time())}_{uuid.uuid4().hex[:6]}"
    control_str = json.dumps(sub.control)
    pit_str = json.dumps(sub.pitConfig) if sub.pitConfig else None
    scenery_str = json.dumps(sub.scenery) if sub.scenery else None

    await db.execute(
        """
        INSERT INTO community_tracks (
            id, name, author, width, biome, control_json,
            pit_config_json, scenery_json, description, likes
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0);
        """,
        (
            track_id,
            sub.name.strip(),
            sub.author.strip(),
            sub.width or 60.0,
            sub.biome or "temperate",
            control_str,
            pit_str,
            scenery_str,
            sub.description or "Community track layout.",
        ),
    )
    await db.commit()

    return {
        "success": True,
        "id": track_id,
        "name": sub.name,
        "message": f"Circuit '{sub.name}' published successfully!",
    }


@router.post("/{track_id}/like", dependencies=[Depends(rate_limit_reactions)])
async def like_community_track(
    track_id: str,
    db: aiosqlite.Connection = Depends(get_db),
):
    """
    Upvote / like a community circuit.
    """
    cursor = await db.execute("SELECT id, likes FROM community_tracks WHERE id = ?;", (track_id,))
    row = await cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Track not found.")

    new_likes = (row["likes"] or 0) + 1
    await db.execute("UPDATE community_tracks SET likes = ? WHERE id = ?;", (new_likes, track_id))
    await db.commit()

    return {"success": True, "trackId": track_id, "likes": new_likes}
