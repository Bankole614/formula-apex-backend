import os
import re
import time
import uuid
from typing import List
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
import aiosqlite

from ..config import settings
from ..database import get_db
from ..schemas.music import MusicTrackItem, PresignedUploadRequest, PresignedUploadResponse
from ..services.r2_storage import r2_service
from ..core.security import verify_admin_key

router = APIRouter(prefix="/api/music", tags=["Music & Cloudflare R2 Streaming"])

AUDIO_EXTS = {".mp3", ".m4a", ".ogg", ".wav"}
R2_SYNC_TTL_SECONDS = 300  # Re-scan R2 music/ bucket at most once every 5 minutes
_last_r2_sync_at: float = 0.0


def _parse_track_from_r2_key(key: str) -> tuple[str, str, str]:
    """Derive deterministic (track_id, artist, title) from an R2 key like 'music/Asake-Forgiveness.mp3'."""
    filename = os.path.basename(key)
    stem, _ = os.path.splitext(filename)
    slug = re.sub(r"[^a-z0-9]+", "_", stem.lower()).strip("_")
    track_id = f"track_{slug}" if slug else f"track_{uuid.uuid4().hex[:8]}"

    # Split on first '-' or ' - ' to separate artist & title
    if " - " in stem:
        artist_raw, title_raw = stem.split(" - ", 1)
    elif "-" in stem:
        artist_raw, title_raw = stem.split("-", 1)
    else:
        artist_raw, title_raw = "Apex Radio", stem

    artist = artist_raw.replace("_", " ").replace("-", " ").strip() or "Apex Radio"
    title = title_raw.replace("_", " ").replace("-", " ").strip() or stem
    return track_id, artist, title


async def sync_r2_music_tracks(db: aiosqlite.Connection, force: bool = False) -> int:
    """
    Discover all audio tracks stored in Cloudflare R2 under 'music/' and insert any
    unregistered tracks into SQLite so GET /api/music/playlist serves the full bucket.
    """
    global _last_r2_sync_at
    if not r2_service.is_configured():
        return 0
    now = time.monotonic()
    if not force and (now - _last_r2_sync_at) < R2_SYNC_TTL_SECONDS:
        return 0

    keys = r2_service.list_objects(prefix="music/")
    _last_r2_sync_at = now
    if not keys:
        return 0

    cursor = await db.execute("SELECT id, r2_key FROM music_tracks;")
    existing_rows = await cursor.fetchall()
    existing_keys = {r["r2_key"] for r in existing_rows if r["r2_key"]}
    existing_ids = {r["id"] for r in existing_rows}

    added = 0
    for idx, key in enumerate(sorted(keys)):
        _, ext = os.path.splitext(key.lower())
        if ext not in AUDIO_EXTS:
            continue
        if key in existing_keys:
            continue

        track_id, artist, title = _parse_track_from_r2_key(key)
        if track_id in existing_ids:
            track_id = f"{track_id}_{uuid.uuid4().hex[:4]}"

        stream_url = r2_service.get_public_url(key)
        await db.execute(
            """
            INSERT OR IGNORE INTO music_tracks (id, title, artist, duration, stream_url, r2_key, is_active, sort_order)
            VALUES (?, ?, ?, 180, ?, ?, 1, ?);
            """,
            (track_id, title, artist, stream_url, key, 10 + idx),
        )
        existing_keys.add(key)
        existing_ids.add(track_id)
        added += 1

    if added > 0:
        await db.commit()
    return added


@router.get("/playlist", response_model=List[MusicTrackItem])
async def get_playlist(db: aiosqlite.Connection = Depends(get_db)):
    """
    Get the official racing music playlist with Cloudflare R2 streaming audio URLs.
    Automatically syncs any newly uploaded tracks from the R2 'music/' folder.
    """
    await sync_r2_music_tracks(db, force=False)
    cursor = await db.execute(
        """
        SELECT id, title, artist, duration, stream_url, r2_key, is_active
        FROM music_tracks
        WHERE is_active = 1
        ORDER BY sort_order ASC, id ASC;
        """
    )
    rows = await cursor.fetchall()
    return [
        MusicTrackItem(
            id=r["id"],
            title=r["title"],
            artist=r["artist"],
            duration=r["duration"],
            streamUrl=r["stream_url"],
            proxyUrl=f"/api/music/stream/{r['id']}" if r["r2_key"] else None,
            isActive=bool(r["is_active"]),
        )
        for r in rows
    ]


@router.post("/sync", dependencies=[Depends(verify_admin_key)])
async def force_sync_r2_music(db: aiosqlite.Connection = Depends(get_db)):
    """Force an immediate re-scan of the Cloudflare R2 'music/' folder (Requires Admin Key)."""
    added = await sync_r2_music_tracks(db, force=True)
    return {"success": True, "added": added}


@router.get("/stream/{track_id}")
async def stream_track(track_id: str, request: Request, db: aiosqlite.Connection = Depends(get_db)):
    """
    Direct HTTP range-streaming audio endpoint from Cloudflare R2 through FastAPI.
    Enables instant audio buffering and playback even if public r2.dev domain access is restricted.
    """
    cursor = await db.execute(
        "SELECT r2_key, stream_url FROM music_tracks WHERE id = ?;",
        (track_id,)
    )
    row = await cursor.fetchone()
    if not row or not row["r2_key"]:
        raise HTTPException(status_code=404, detail="Track not found or has no R2 key.")

    range_header = request.headers.get("range")
    r2_obj = r2_service.get_object(row["r2_key"], range_header)
    if not r2_obj:
        raise HTTPException(status_code=502, detail="Failed to retrieve audio stream from Cloudflare R2.")

    body = r2_obj["Body"]
    status_code = 206 if range_header else 200
    headers = {
        "Accept-Ranges": "bytes",
        "Content-Type": r2_obj.get("ContentType", "audio/mpeg"),
        "Cache-Control": "public, max-age=31536000, immutable",
    }
    if "ContentLength" in r2_obj:
        headers["Content-Length"] = str(r2_obj["ContentLength"])
    if "ContentRange" in r2_obj:
        headers["Content-Range"] = str(r2_obj["ContentRange"])

    def iter_stream():
        try:
            while chunk := body.read(64 * 1024):
                yield chunk
        finally:
            body.close()

    return StreamingResponse(iter_stream(), status_code=status_code, headers=headers)


@router.post(
    "/presigned-upload",
    response_model=PresignedUploadResponse,
    dependencies=[Depends(verify_admin_key)],
)
async def get_presigned_upload_url(req: PresignedUploadRequest):
    """
    Generate a direct presigned upload URL to Cloudflare R2 (Requires Admin Key).
    Allows uploading new songs directly to Cloudflare without routing heavy binary files through the FastAPI server.
    """
    clean_name = req.filename.replace(" ", "_")
    key = f"{req.category}/{int(uuid.uuid4().int % 1000000)}_{clean_name}"

    if r2_service.is_configured():
        upload_url = r2_service.generate_presigned_upload_url(
            key=key, content_type=req.contentType
        )
        if not upload_url:
            raise HTTPException(status_code=500, detail="Failed to generate R2 presigned URL.")
        public_url = r2_service.get_public_url(key)
    else:
        # Mock / Fallback URL when R2 keys are not yet configured in .env
        upload_url = f"https://mock-r2.local/upload/{key}"
        public_url = f"{settings.R2_PUBLIC_URL}/{key}"

    return PresignedUploadResponse(
        uploadUrl=upload_url,
        publicUrl=public_url,
        key=key,
    )


@router.post(
    "/register",
    dependencies=[Depends(verify_admin_key)],
)
async def register_music_track(
    title: str,
    artist: str,
    streamUrl: str,
    duration: int = 180,
    r2Key: str = "",
    db: aiosqlite.Connection = Depends(get_db),
):
    """
    Register a newly uploaded R2 audio track into the active in-game radio playlist (Requires Admin Key).
    """
    track_id = f"track_{uuid.uuid4().hex[:8]}"
    await db.execute(
        """
        INSERT INTO music_tracks (id, title, artist, duration, stream_url, r2_key, is_active, sort_order)
        VALUES (?, ?, ?, ?, ?, ?, 1, 99);
        """,
        (track_id, title, artist, duration, streamUrl, r2Key),
    )
    await db.commit()
    return {"success": True, "trackId": track_id, "title": title, "streamUrl": streamUrl}
