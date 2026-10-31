from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import settings
from app.database import init_db
from app.routers import leaderboard, tracks, career, music, multiplayer


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Ensure database schema, indexes and seed records are created
    await init_db()
    yield
    # Shutdown logic (if any)


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="High-performance backend API powering Apex Racing GP: global leaderboards, ghost telemetry, community tracks, career cloud sync, and Cloudflare R2 audio streaming.",
    lifespan=lifespan,
)

# Configure Cross-Origin Resource Sharing (CORS) for game clients
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register Feature Routers
app.include_router(leaderboard.router)
app.include_router(tracks.router)
app.include_router(career.router)
app.include_router(music.router)
app.include_router(multiplayer.router)
app.add_api_websocket_route("/ws/multiplayer/{room_id}", multiplayer.multiplayer_ws)


@app.get("/api/health", tags=["System"])
async def health_check():
    """System health check endpoint."""
    return {
        "status": "online",
        "service": settings.APP_NAME,
        "version": settings.APP_VERSION,
    }


@app.get("/", tags=["System"])
async def root():
    """API overview and documentation links."""
    return JSONResponse(
        {
            "message": "Welcome to Apex Racing GP Backend API",
            "docs": "/docs",
            "openapi": "/openapi.json",
            "health": "/api/health",
        }
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG,
    )

