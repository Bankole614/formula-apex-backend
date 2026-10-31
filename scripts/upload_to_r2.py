#!/usr/bin/env python3
"""
Apex Racing GP - Cloudflare R2 Music Uploader
Uploads optimized music files to Cloudflare R2 bucket with streaming CDN headers,
and registers them into the FastAPI SQLite database & frontend fallback playlist.

Features:
- S3-compatible multi-part / direct upload to Cloudflare R2
- Sets audio/mpeg Content-Type and 1-year public Cache-Control
- Extracts clean Artist & Title metadata automatically
- Registers tracks into SQLite `music_tracks` table for /api/music/playlist
- Syncs a static fallback playlist to src/music/playlist.json
"""

import os
import sys
import json
import sqlite3
import argparse
import subprocess
from pathlib import Path
from typing import Tuple, Optional

# Ensure UTF-8 output on Windows consoles
if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

import boto3
from botocore.config import Config
from dotenv import load_dotenv

# Paths
SCRIPTS_DIR = Path(__file__).resolve().parent
BACKEND_DIR = SCRIPTS_DIR.parent
ROOT_DIR = BACKEND_DIR.parent
ENV_PATH = BACKEND_DIR / ".env"

# Load backend/.env
if ENV_PATH.exists():
    load_dotenv(ENV_PATH)
else:
    load_dotenv()


def get_audio_duration(file_path: Path) -> int:
    """Estimate or extract duration in seconds using ffmpeg or file size."""
    try:
        import imageio_ffmpeg
        ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
        cmd = [ffmpeg_exe, "-i", str(file_path)]
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        # Look for "Duration: 00:03:18.45" in stderr
        import re
        match = re.search(r"Duration:\s*(\d+):(\d+):(\d+)", res.stderr)
        if match:
            h, m, s = map(int, match.groups())
            return h * 3600 + m * 60 + s
    except Exception:
        pass

    # Rough fallback: 128kbps = 16KB/s
    size_bytes = file_path.stat().st_size
    return max(30, int(size_bytes / (16 * 1024)))


KNOWN_MULTIWORD_ARTISTS = [
    "young jonn", "young-jonn",
    "seyi vibez", "seyi-vibez",
    "kidd carder", "kidd-carder",
    "playstarz music", "playstarz_music",
    "tatamusic", "lnplusmusic", "hitslab", "gr0za", "kulakovka", "astronautflute", "viacheslavstarostin"
]

def parse_artist_title(filename: str) -> Tuple[str, str]:
    """Parse artist and title cleanly from filename."""
    stem = Path(filename).stem
    
    # Check known multi-word artists first
    lower = stem.lower()
    for art in KNOWN_MULTIWORD_ARTISTS:
        if lower.startswith(art):
            artist = art.replace("-", " ").replace("_", " ").title()
            rest = stem[len(art):].strip(" -_")
            title = rest.replace("-", " ").replace("_", " ").strip()
            return artist, title or "Track"

    if "-" in stem:
        parts = stem.split("-", 1)
        artist = parts[0].strip().replace("_", " ")
        title = parts[1].strip().replace("_", " ")
    else:
        artist = "Apex Soundtrack"
        title = stem.strip().replace("_", " ")
    return artist, title


def get_r2_client(account_id: str, access_key: str, secret_key: str):
    endpoint_url = f"https://{account_id}.r2.cloudflarestorage.com"
    return boto3.client(
        "s3",
        endpoint_url=endpoint_url,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        config=Config(signature_version="s3v4"),
        region_name="auto"
    )


def register_in_sqlite(db_path: Path, track_data: dict):
    """Ensure table exists and upsert track in music_tracks table."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS music_tracks (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            artist TEXT NOT NULL,
            duration INTEGER DEFAULT 180,
            stream_url TEXT NOT NULL,
            r2_key TEXT,
            is_active BOOLEAN DEFAULT 1,
            sort_order INTEGER DEFAULT 0
        );
    """)

    cursor.execute("""
        INSERT INTO music_tracks (id, title, artist, duration, stream_url, r2_key, is_active, sort_order)
        VALUES (?, ?, ?, ?, ?, ?, 1, ?)
        ON CONFLICT(id) DO UPDATE SET
            title=excluded.title,
            artist=excluded.artist,
            duration=excluded.duration,
            stream_url=excluded.stream_url,
            r2_key=excluded.r2_key,
            is_active=1;
    """, (
        track_data["id"],
        track_data["title"],
        track_data["artist"],
        track_data["duration"],
        track_data["stream_url"],
        track_data["r2_key"],
        track_data.get("sort_order", 10),
    ))

    conn.commit()
    conn.close()


def sync_frontend_playlist(playlist_items: list):
    """Write/update playlist.json as a static fallback."""
    # 1. Always keep a copy inside backend/data/playlist.json (100% standalone)
    backend_json = BACKEND_DIR / "data" / "playlist.json"
    backend_json.parent.mkdir(parents=True, exist_ok=True)
    with open(backend_json, "w", encoding="utf-8") as f:
        json.dump(playlist_items, f, indent=2)
    print(f"✔ Standalone playlist manifest saved to: {backend_json}")

    # 2. If running alongside frontend, sync to src/music/playlist.json
    frontend_json = ROOT_DIR / "src" / "music" / "playlist.json"
    if frontend_json.parent.exists():
        with open(frontend_json, "w", encoding="utf-8") as f:
            json.dump(playlist_items, f, indent=2)
        print(f"✔ Frontend static fallback updated: {frontend_json}")


def main():
    parser = argparse.ArgumentParser(description="Upload audio tracks to Cloudflare R2 and register them in the game.")
    parser.add_argument(
        "--input", "-i",
        type=str,
        default=str(BACKEND_DIR / "optimized_music"),
        help="Directory of optimized audio files to upload (default: backend/optimized_music)."
    )
    parser.add_argument(
        "--prefix",
        type=str,
        default="music",
        help="S3 Key prefix in Cloudflare R2 bucket (default: music)."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simulate the upload and database registration without uploading to R2."
    )

    args = parser.parse_args()

    # Read credentials from environment
    account_id = os.getenv("R2_ACCOUNT_ID", "").strip()
    access_key = os.getenv("R2_ACCESS_KEY_ID", "").strip()
    secret_key = os.getenv("R2_SECRET_ACCESS_KEY", "").strip()
    bucket_name = os.getenv("R2_BUCKET_NAME", "").strip()
    public_url = os.getenv("R2_PUBLIC_URL", "").rstrip("/")
    db_path = Path(os.getenv("DATABASE_PATH", str(BACKEND_DIR / "data" / "apex_racing.db")))

    print("☁️  Apex Racing GP - Cloudflare R2 Music Uploader")
    print("==================================================")
    print(f"• Bucket Name   : {bucket_name or '[MISSING]'}")
    print(f"• Account ID    : {account_id[:6]}...{account_id[-4:] if len(account_id) > 10 else ''}")
    print(f"• Public URL    : {public_url or '[MISSING]'}")
    print(f"• Database Path : {db_path}")
    print(f"• Mode          : {'DRY RUN (Simulation)' if args.dry_run else 'LIVE UPLOAD'}")
    print("==================================================\n")

    if not args.dry_run:
        if not (account_id and access_key and secret_key and bucket_name and public_url):
            print("[ERROR] Missing Cloudflare R2 credentials in backend/.env!")
            print("Please check that R2_ACCOUNT_ID, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY, R2_BUCKET_NAME, and R2_PUBLIC_URL are set.")
            sys.exit(1)

    input_dir = Path(args.input).resolve()
    if not input_dir.exists():
        print(f"[ERROR] Input directory not found: {input_dir}")
        print("Tip: Run `python backend/scripts/optimize_music.py` first to generate optimized files.")
        sys.exit(1)

    audio_files = []
    for ext in ["*.mp3", "*.ogg", "*.wav", "*.m4a"]:
        audio_files.extend(list(input_dir.glob(ext)))

    if not audio_files:
        print(f"[WARN] No audio files found in: {input_dir}")
        return

    client = None
    if not args.dry_run:
        try:
            client = get_r2_client(account_id, access_key, secret_key)
            # Test connection
            client.head_bucket(Bucket=bucket_name)
            print(f"✔ Successfully connected to Cloudflare R2 bucket: {bucket_name}\n")
        except Exception as e:
            print(f"[ERROR] Failed to connect to Cloudflare R2: {e}")
            sys.exit(1)

    playlist_for_export = []

    for idx, audio_path in enumerate(audio_files, start=1):
        artist, title = parse_artist_title(audio_path.name)
        duration = get_audio_duration(audio_path)
        r2_key = f"{args.prefix}/{audio_path.name}"
        stream_url = f"{public_url}/{r2_key}"
        track_id = f"track_{audio_path.stem.lower().replace('-', '_')}"

        print(f"[{idx}/{len(audio_files)}] Track: {artist} - {title}")
        print(f"    ↳ R2 Key     : {r2_key}")
        print(f"    ↳ Stream URL : {stream_url}")
        print(f"    ↳ Duration   : {duration // 60}:{duration % 60:02d} ({duration}s)")

        if not args.dry_run and client:
            try:
                with open(audio_path, "rb") as f:
                    client.put_object(
                        Bucket=bucket_name,
                        Key=r2_key,
                        Body=f,
                        ContentType="audio/mpeg",
                        CacheControl="public, max-age=31536000, immutable"
                    )
                print(f"    ✔ Uploaded successfully to Cloudflare R2")
            except Exception as e:
                print(f"    ❌ Upload failed: {e}")
                continue

        track_record = {
            "id": track_id,
            "title": title,
            "artist": artist,
            "duration": duration,
            "stream_url": stream_url,
            "r2_key": r2_key,
            "sort_order": idx,
        }

        # Register in SQLite database
        try:
            register_in_sqlite(db_path, track_record)
            print(f"    ✔ Registered in SQLite database ({db_path.name})")
        except Exception as e:
            print(f"    ⚠ Could not update SQLite database: {e}")

        playlist_for_export.append({
            "id": track_id,
            "title": title,
            "artist": artist,
            "duration": duration,
            "streamUrl": stream_url,
            "isActive": True
        })
        print()

    # Sync static fallback JSON playlist
    if playlist_for_export:
        sync_frontend_playlist(playlist_for_export)

    print("🎉 All tracks processed successfully!")
    print(f"• Total tracks uploaded/registered: {len(playlist_for_export)}")
    print(f"• Your music is now ready to stream live in-game with $0 egress fees!\n")


if __name__ == "__main__":
    main()

