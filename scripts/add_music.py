#!/usr/bin/env python3
"""
Apex Racing GP - All-in-One Music Importer
One simple command to add new songs to the game:
1. Optimizes the audio (128kbps stereo, -16 LUFS loudness normalized, artwork stripped)
2. Uploads the song to your Cloudflare R2 bucket
3. Registers the track in the SQLite database and syncs the in-game playlist

Usage:
  # Import all new tracks in src/music:
  python backend/scripts/add_music.py

  # Or import a single file from anywhere on your PC:
  python backend/scripts/add_music.py "C:\\path\\to\\Artist-SongName.mp3"
"""

import sys
import argparse
from pathlib import Path

# Ensure UTF-8 output on Windows consoles
if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

# Add backend directory to sys.path
SCRIPTS_DIR = Path(__file__).resolve().parent
BACKEND_DIR = SCRIPTS_DIR.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

# Import the existing optimizer and uploader modules
from scripts.optimize_music import (
    get_ffmpeg_binary,
    clean_filename,
    optimize_audio_file,
    format_bytes,
    DEFAULT_INPUT,
)
from scripts.upload_to_r2 import (
    parse_artist_title,
    get_audio_duration,
    get_r2_client,
    register_in_sqlite,
    sync_frontend_playlist,
    os,
)


def main():
    parser = argparse.ArgumentParser(description="One-step tool to optimize, upload to Cloudflare R2, and register songs.")
    parser.add_argument(
        "song_path",
        nargs="?",
        default=None,
        help="Optional path to a single audio file or folder to import (defaults to scanning src/music)."
    )
    parser.add_argument(
        "--bitrate", "-b",
        default="128k",
        choices=["96k", "128k", "160k", "192k"],
        help="Audio bitrate (default: 128k)."
    )
    args = parser.parse_args()

    input_target = Path(args.song_path).resolve() if args.song_path else DEFAULT_INPUT
    output_dir = BACKEND_DIR / "optimized_music"
    output_dir.mkdir(parents=True, exist_ok=True)

    # 1. Collect files to process
    audio_files = []
    if input_target.is_file():
        audio_files.append(input_target)
    elif input_target.is_dir():
        for ext in ["*.mp3", "*.wav", "*.m4a", "*.ogg", "*.flac"]:
            audio_files.extend(list(input_target.glob(ext)))
    else:
        print(f"[ERROR] Path does not exist: {input_target}")
        sys.exit(1)

    if not audio_files:
        print(f"[WARN] No audio files found in: {input_target}")
        return

    print("🎵 Apex Racing GP - One-Step Music Importer")
    print("============================================")
    print(f"• Input target  : {input_target}")
    print(f"• Tracks found  : {len(audio_files)}")
    print(f"• Target bitrate: {args.bitrate}")
    print("============================================\n")

    # 2. Setup R2 credentials & client
    account_id = os.getenv("R2_ACCOUNT_ID", "").strip()
    access_key = os.getenv("R2_ACCESS_KEY_ID", "").strip()
    secret_key = os.getenv("R2_SECRET_ACCESS_KEY", "").strip()
    bucket_name = os.getenv("R2_BUCKET_NAME", "apex-racing-assets").strip()
    public_url = os.getenv("R2_PUBLIC_URL", "").rstrip("/")
    db_path = Path(os.getenv("DATABASE_PATH", str(BACKEND_DIR / "data" / "apex_racing.db")))

    client = None
    if account_id and access_key and secret_key:
        try:
            client = get_r2_client(account_id, access_key, secret_key)
            print(f"✔ Connected to Cloudflare R2 bucket: {bucket_name}")
        except Exception as e:
            print(f"[WARN] Cloudflare R2 connection failed: {e}. Running local optimization only.")
    else:
        print("[WARN] Cloudflare credentials not set in backend/.env. Running local optimization only.")

    ffmpeg_exe = get_ffmpeg_binary()
    existing_optimized = {f.name.lower() for f in output_dir.glob("*.mp3")}
    playlist_items = []

    # 3. Process each track: Optimize -> Upload -> Register
    for idx, audio_file in enumerate(audio_files, start=1):
        clean_name = clean_filename(audio_file.name, existing_optimized)
        opt_path = output_dir / clean_name
        orig_size = audio_file.stat().st_size

        print(f"\n[{idx}/{len(audio_files)}] 🎧 Processing: {audio_file.name}")
        
        # Optimize
        success = optimize_audio_file(
            input_path=audio_file,
            output_path=opt_path,
            ffmpeg_exe=ffmpeg_exe,
            bitrate=args.bitrate,
            normalize_loudness=True
        )

        if not success or not opt_path.exists():
            print(f"    ❌ Optimization failed for {audio_file.name}")
            continue

        opt_size = opt_path.stat().st_size
        saved_pct = ((orig_size - opt_size) / orig_size) * 100
        print(f"    ✔ Compressed: {format_bytes(orig_size)} ➔ {format_bytes(opt_size)} ({saved_pct:.1f}% saved)")

        # Upload to R2
        artist, title = parse_artist_title(opt_path.name)
        duration = get_audio_duration(opt_path)
        r2_key = f"music/{clean_name}"
        stream_url = f"{public_url}/{r2_key}" if public_url else r2_key
        track_id = f"track_{opt_path.stem.lower().replace('-', '_')}"

        if client:
            try:
                with open(opt_path, "rb") as f:
                    client.put_object(
                        Bucket=bucket_name,
                        Key=r2_key,
                        Body=f,
                        ContentType="audio/mpeg",
                        CacheControl="public, max-age=31536000, immutable"
                    )
                print(f"    ✔ Uploaded to Cloudflare R2 ({r2_key})")
            except Exception as e:
                print(f"    ⚠ Upload error: {e}")

        # Register in SQLite database
        track_record = {
            "id": track_id,
            "title": title,
            "artist": artist,
            "duration": duration,
            "stream_url": stream_url,
            "r2_key": r2_key,
            "sort_order": 99,
        }
        try:
            register_in_sqlite(db_path, track_record)
            print(f"    ✔ Registered in SQLite database ({title} by {artist})")
        except Exception as e:
            print(f"    ⚠ Database registration warning: {e}")

        playlist_items.append({
            "id": track_id,
            "title": title,
            "artist": artist,
            "duration": duration,
            "streamUrl": stream_url,
            "isActive": True
        })

    # Update in-game static fallback playlist
    if playlist_items:
        sync_frontend_playlist(playlist_items)

    print("\n🎉 Import complete! Your songs are ready to play.")


if __name__ == "__main__":
    main()

