# Apex Racing GP — FastAPI Backend & Cloudflare R2 Audio

High-performance Python/FastAPI backend powering **Apex Racing GP**:
- 🏆 **Global Circuit Leaderboards**: Lap times, anti-cheat physics validation, and ghost lap replay telemetry.
- 🎨 **Community Paddock (Track Hub)**: Publish, browse, and upvote custom circuits designed in Circuit Architect.
- 🎮 **Career Cloud Sync**: Sync driver licenses, XP levels, and R&D upgrades across mobile and desktop.
- 🎵 **Cloudflare R2 Music Streaming**: High-speed, \$0 egress streaming for in-game soundtrack and 3D assets.

---

## 1. Quickstart (Run Locally)

### Prerequisites
- Python 3.10+ installed

### Setup & Run

1. Navigate to the `backend/` folder:
   ```bash
   cd backend
   ```

2. Create a virtual environment:
   ```bash
   python -m venv venv
   # On Windows:
   .\venv\Scripts\activate
   # On Linux / macOS:
   source venv/bin/activate
   ```

3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

4. Launch the server:
   ```bash
   python run.py
   # Or using uvicorn directly:
   uvicorn main:app --reload --port 8000
   ```

5. Visit the interactive Swagger API documentation in your browser:
   👉 **http://localhost:8000/docs**

---

## 2. Cloudflare R2: Why It's the Best Choice for Game Music

### Why You Should Use Cloudflare R2 for Songs:
1. **$0 Egress (Free Bandwidth)**:
   - AWS S3 charges ~\$0.09 per GB downloaded. If 1,000 players stream 4MB songs throughout a session, S3 bills hundreds of dollars.
   - **Cloudflare R2 has ZERO egress fees**. You can stream petabytes of audio to millions of players with \$0 bandwidth cost.
2. **Global Edge CDN**:
   - Songs are cached directly at Cloudflare edge servers near the player (Lagos, London, Frankfurt, Singapore, etc.). Audio starts playing in milliseconds.
3. **HTTP 206 Range Streaming**:
   - Web browsers use HTTP Range headers (`Range: bytes=0-1048576`). R2 streams audio in lightweight chunks, so mobile devices don't have to download the full 4MB file before the music starts playing.
4. **Keeps the Web App Tiny**:
   - Removes heavy `.mp3` files from your Git repo and static bundle, making deployments fast and lightweight.

---

## 3. How to Set Up Cloudflare R2 for Your Songs

1. Log in to the [Cloudflare Dashboard](https://dash.cloudflare.com/) and go to **R2**.
2. Click **Create Bucket** and name it (e.g. `apex-racing-assets`).
3. Under **Settings -> Public Access**:
   - Click **Connect Domain** to link your custom domain (e.g. `cdn.yourgame.com`), or enable **R2.dev subdomain**.
4. Upload or stream your songs using the automated Python scripts:
   - **Optimize MP3s**: `python scripts/optimize_music.py` (re-encodes to 128kbps, strips bloated album art, normalizes loudness)
   - **Upload to Cloudflare R2**: `python scripts/upload_to_r2.py` (uploads with CDN caching headers & registers tracks in SQLite)
5. Enable public access on your R2 bucket:
   - In Cloudflare Dashboard -> **R2** -> Bucket `corpus-images` -> **Settings** -> **Public Access** -> **R2.dev subdomain**: click **"Allow Access"** (or connect a custom domain).
   - FastAPI also includes a built-in proxy streaming endpoint (`/api/music/stream/{track_id}`) supporting HTTP 206 range buffering.

---

## 4. Audio Tooling Scripts

### ⭐ One-Step Importer (`scripts/add_music.py`) — Recommended!
Add, compress, upload to Cloudflare R2, and register in the database all in **one command**:
```bash
# Add any single song from your computer:
python scripts/add_music.py "C:\path\to\Artist-SongName.mp3"

# Or scan and process all songs in src/music:
python scripts/add_music.py
```

---

### Individual Step Scripts:

#### 1. Optimize MP3s (`scripts/optimize_music.py`)
```bash
python scripts/optimize_music.py --input ../src/music --output optimized_music --bitrate 128k
```
- Re-encodes audio with high-quality MP3 (`libmp3lame`).
- Strips heavy ID3 frames and embedded high-res cover art (saving 35-60% file size).
- Applies broadcast loudness normalization (`-16 LUFS`) so all music plays at balanced game volume.

#### 2. Upload to Cloudflare R2 (`scripts/upload_to_r2.py`)
```bash
python scripts/upload_to_r2.py --input optimized_music
```
- Multi-part S3 upload to your R2 bucket with `Cache-Control: public, max-age=31536000, immutable`.
- Auto-extracts Artist & Title from filenames.
- Registers tracks directly into SQLite database for `GET /api/music/playlist`.
- Generates a static `src/music/playlist.json` fallback for offline play.

---

## 5. API Endpoints Reference

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `GET` | `/api/leaderboard?track={name}` | Fetch top lap records for a circuit |
| `POST` | `/api/leaderboard` | Submit a lap time (with anti-cheat check) |
| `GET` | `/api/leaderboard/ghost/{id}` | Fetch tick-by-tick ghost telemetry |
| `GET` | `/api/community-tracks` | Browse published user-created circuits |
| `POST` | `/api/community-tracks` | Publish a track from Circuit Architect |
| `POST` | `/api/community-tracks/{id}/like` | Upvote / like a community track |
| `GET` | `/api/career/{user_id}` | Fetch career progress, XP, and R&D points |
| `POST` | `/api/career/{user_id}/sync` | Sync career level and upgrades to cloud |
| `GET` | `/api/music/playlist` | Fetch active in-game music playlist (R2 URLs) |
| `POST` | `/api/music/presigned-upload` | Generate presigned upload URL to R2 |
| `GET` | `/api/health` | Backend status health check |

---

## 5. Free / Low-Cost Deployment Options

- **Railway / Render**: Deploy in one click by connecting your GitHub repo and pointing the root directory to `backend/`.
- **Fly.io**: Run as a lightweight container with persistent volume for SQLite.
- **VPS (Hetzner / DigitalOcean)**: Run using `systemd` or `docker-compose`.

