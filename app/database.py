import json
import os
import aiosqlite
from .config import settings

DB_FILE = settings.DATABASE_PATH


async def get_db():
    """Async database connection dependency / context manager."""
    os.makedirs(os.path.dirname(DB_FILE), exist_ok=True)
    async with aiosqlite.connect(DB_FILE) as db:
        db.row_factory = aiosqlite.Row
        yield db


async def init_db():
    """Create database tables and seed default circuits and track records on startup."""
    os.makedirs(os.path.dirname(DB_FILE), exist_ok=True)
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("PRAGMA journal_mode = WAL;")
        await db.execute("PRAGMA foreign_keys = ON;")

        # Leaderboards Table
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS leaderboards (
                id TEXT PRIMARY KEY,
                track_name TEXT NOT NULL,
                driver_name TEXT NOT NULL,
                team_name TEXT DEFAULT 'Apex GP',
                car_color TEXT DEFAULT '#e10600',
                time_ticks INTEGER NOT NULL,
                time_formatted TEXT NOT NULL,
                sectors_json TEXT,
                compound TEXT DEFAULT 'M',
                has_ghost BOOLEAN DEFAULT 0,
                ghost_data_json TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """
        )
        await db.execute(
            "CREATE INDEX IF NOT EXISTS idx_leaderboards_track ON leaderboards (track_name, time_ticks);"
        )

        # Community Tracks Table (Custom circuits published from Circuit Architect)
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS community_tracks (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                author TEXT NOT NULL,
                width REAL DEFAULT 60.0,
                biome TEXT DEFAULT 'temperate',
                control_json TEXT NOT NULL,
                pit_config_json TEXT,
                scenery_json TEXT,
                description TEXT,
                likes INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """
        )

        # Career Cloud Profiles (Sync Driver License, XP, R&D points across devices)
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS career_profiles (
                user_id TEXT PRIMARY KEY,
                driver_name TEXT NOT NULL,
                team_id TEXT DEFAULT 'scuderia',
                level INTEGER DEFAULT 1,
                xp INTEGER DEFAULT 0,
                rd_points INTEGER DEFAULT 0,
                upgrades_json TEXT,
                stats_json TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """
        )

        # Music Playlist (Streamed from Cloudflare R2 or local CDN)
        await db.execute(
            """
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
            """
        )

        # Seed initial sample music tracks (referencing Cloudflare R2 endpoints)
        cursor = await db.execute("SELECT COUNT(*) FROM music_tracks;")
        count = (await cursor.fetchone())[0]
        if count == 0:
            sample_tracks = [
                (
                    "track_slick",
                    "SLICK",
                    "Victony",
                    162,
                    f"{settings.R2_PUBLIC_URL}/music/Victony-SLICK.mp3",
                    "music/Victony-SLICK.mp3",
                    1,
                    1,
                ),
                (
                    "track_online",
                    "Online",
                    "BNXN",
                    198,
                    f"{settings.R2_PUBLIC_URL}/music/BNXN-Online.mp3",
                    "music/BNXN-Online.mp3",
                    1,
                    2,
                ),
            ]
            await db.executemany(
                """
                INSERT INTO music_tracks (id, title, artist, duration, stream_url, r2_key, is_active, sort_order)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?);
                """,
                sample_tracks,
            )

        # Seed initial sample community track
        cursor = await db.execute("SELECT COUNT(*) FROM community_tracks;")
        count = (await cursor.fetchone())[0]
        if count == 0:
            sample_control = [
                {"x": -260, "y": 0},
                {"x": -180, "y": 140},
                {"x": 40, "y": 160},
                {"x": 240, "y": 60},
                {"x": 260, "y": -90},
                {"x": 90, "y": -170},
                {"x": -150, "y": -140},
            ]
            await db.execute(
                """
                INSERT INTO community_tracks (id, name, author, width, biome, control_json, description, likes)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    "track_monza_apex",
                    "Autodromo Nazionale Apex",
                    "Scuderia Architect",
                    68.0,
                    "monza",
                    json.dumps(sample_control),
                    "High-speed temple of velocity with iconic chicanes and slipstream straights.",
                    18,
                ),
            )

        await db.commit()

