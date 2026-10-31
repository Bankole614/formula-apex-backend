from typing import Dict, Any, Optional
from pydantic import BaseModel, Field


class CareerSyncRequest(BaseModel):
    userId: str = Field(..., min_length=4)
    driverName: str
    teamId: str = "scuderia"
    level: int = 1
    xp: int = 0
    rdPoints: int = 0
    upgrades: Dict[str, int] = Field(default_factory=dict)
    stats: Dict[str, Any] = Field(default_factory=dict)
    # Optional authentication token / player signature for identity verification
    authToken: Optional[str] = None


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

