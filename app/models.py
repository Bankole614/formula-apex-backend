from typing import List, Optional, Any, Dict
from pydantic import BaseModel, Field


# ----------------- Leaderboard Schemas -----------------
class LeaderboardSubmission(BaseModel):
    trackName: str = Field(..., description="Name or identifier of the track")
    driverName: str = Field(..., min_length=2, max_length=32)
    teamName: Optional[str] = "Apex GP"
    carColor: Optional[str] = "#e10600"
    timeTicks: int = Field(..., gt=100, description="Lap duration in 60 FPS physics ticks")
    timeFormatted: str = Field(..., description="E.g. '1:18.420'")
    sectors: Optional[List[float]] = None
    compound: Optional[Any] = "M"
    ghostData: Optional[List[Dict[str, Any]]] = None  # Telemetry replay frames (x, y, heading, speed)


class LeaderboardEntryResponse(BaseModel):
    id: str
    trackName: str
    driverName: str
    teamName: str
    carColor: str
    timeTicks: int
    timeFormatted: str
    sectors: Optional[List[float]] = None
    compound: str
    date: str
    hasGhost: bool


# ----------------- Community Circuit Schemas -----------------
class CommunityTrackSubmission(BaseModel):
    name: str = Field(..., min_length=3, max_length=48)
    author: str = Field(..., min_length=2, max_length=32)
    control: List[Dict[str, float]] = Field(..., min_length=4)
    width: Optional[float] = 60.0
    biome: Optional[str] = "temperate"
    pitConfig: Optional[Dict[str, Any]] = None
    scenery: Optional[List[Dict[str, Any]]] = None
    description: Optional[str] = "Community custom layout."


class CommunityTrackResponse(BaseModel):
    id: str
    name: str
    author: str
    width: float
    biome: str
    control: List[Dict[str, float]]
    pitConfig: Optional[Dict[str, Any]] = None
    scenery: Optional[List[Dict[str, Any]]] = None
    description: str
    date: str
    likes: int


# ----------------- Career Cloud Sync Schemas -----------------
class CareerSyncRequest(BaseModel):
    userId: str = Field(..., min_length=4)
    driverName: str
    teamId: str = "scuderia"
    level: int = 1
    xp: int = 0
    rdPoints: int = 0
    upgrades: Dict[str, int] = Field(default_factory=dict)
    stats: Dict[str, Any] = Field(default_factory=dict)


class CareerProfileResponse(BaseModel):
    userId: str
    driverName: str
    teamId: str
    level: int
    xp: int
    rdPoints: int
    upgrades: Dict[str, int]
    stats: Dict[str, Any]
    updatedAt: str


# ----------------- Music & Audio Schemas -----------------
class MusicTrackItem(BaseModel):
    id: str
    title: str
    artist: str
    duration: int
    streamUrl: str
    proxyUrl: Optional[str] = None
    isActive: bool = True


class PresignedUploadRequest(BaseModel):
    filename: str
    contentType: str = "audio/mpeg"
    category: str = "music"  # 'music', 'models', 'ghosts'


class PresignedUploadResponse(BaseModel):
    uploadUrl: str
    publicUrl: str
    key: str

