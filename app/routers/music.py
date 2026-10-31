import uuid
from typing import List
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
import aiosqlite

from ..config import settings
from ..database import get_db
from ..models import MusicTrackItem, PresignedUploadRequest, PresignedUploadResponse
from ..services.r2_storage import r2_service

router = APIRouter(prefix="/api/music", tags=["Music & Cloudflare R2 Streaming"])


@router.get("/playlist", response_model=List[MusicTrackItem])
async def get_playlist(db: aiosqlite.Connection = Depends(get_db)):
    """
    Get the official racing music playlist with Cloudflare R2 streaming audio URLs.
    Includes both direct CDN streamUrl and resilient backend proxyUrl.
    """
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


@router.post("/presigned-upload", response_model=PresignedUploadResponse)
async def get_presigned_upload_url(req: PresignedUploadRequest):
    """
    Generate a direct presigned upload URL to Cloudflare R2.
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


@router.post("/register")
async def register_music_track(
    title: str,
    artist: str,
    streamUrl: str,
    duration: int = 180,
    r2Key: str = "",
    db: aiosqlite.Connection = Depends(get_db),
):
    """
    Register a newly uploaded R2 audio track into the active in-game radio playlist.
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

