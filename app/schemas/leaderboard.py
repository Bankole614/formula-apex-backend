from typing import List, Optional, Any, Dict
from pydantic import BaseModel, Field


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

